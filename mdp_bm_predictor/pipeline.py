from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import SimpleITK as sitk
from PIL import ImageDraw

from .annotation_utils import build_circle_mask_image, display_circle_to_raw, display_rect_to_canvas
from .assets_loader import load_model_assets
from .config import ACQUISITION_VIEW_LABELS, CANVAS_HEIGHT
from .deep_client import run_deep_feature_worker
from .image_utils import build_render_bundle, read_wbs_image
from .predictors import (
    classify_probability,
    compute_diagnostic_contributions,
    compute_diagnostic_probability,
    compute_linear_score,
    compute_radscore_contributions,
    compute_total_points,
    standardize_features,
)
from .radiomics_utils import extract_selected_radiomics


@dataclass
class PredictionRequest:
    nii_path: Path
    output_root: Path
    age: float
    acquisition_view: int
    circle_display: dict[str, float]
    rect_display: dict[str, float]


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)


def _slugify_case_name(path: Path) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in path.stem) or "case"


def _prepare_output_dir(output_root: Path, nii_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_name = _slugify_case_name(nii_path)
    output_dir = output_root / f"{case_name}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _risk_label(total_points: float, threshold: float) -> str:
    return "High risk" if total_points >= threshold else "Low risk"


def _build_prognosis_calls(total_points: float, thresholds: dict[str, float]) -> dict[str, dict[str, float | str]]:
    return {
        name: {
            "threshold": float(threshold),
            "label": _risk_label(total_points, float(threshold)),
        }
        for name, threshold in thresholds.items()
    }


def _save_annotation_preview(
    bundle,
    circle_display: dict[str, float],
    rect_display: dict[str, float],
    output_path: Path,
) -> None:
    preview = bundle.canvas_image.copy()
    draw = ImageDraw.Draw(preview)

    cx = circle_display["center_x"]
    cy = circle_display["center_y"]
    radius = circle_display["radius"]
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="#f97316", width=4)

    left = rect_display["left"]
    top = rect_display["top"]
    right = left + rect_display["width"]
    bottom = top + rect_display["height"]
    draw.rectangle((left, top, right, bottom), outline="#14b8a6", width=4)

    preview.save(output_path)


def _write_summary_text(result: dict, output_path: Path) -> None:
    acquisition_view = int(result["acquisition_view"])
    acquisition_view_label = ACQUISITION_VIEW_LABELS.get(acquisition_view, "Unknown")
    lines = [
        "MDP Bone Lesion Predictor",
        "",
        f"Input image: {result['input_image']}",
        f"Age: {result['age']}",
        f"Acquisition view: {acquisition_view_label} (code {acquisition_view})",
        "",
        f"Radscore: {result['radscore']:.6f}",
        f"Diagnostic probability: {result['diagnostic_probability']:.4f}",
        f"Diagnostic label: {result['diagnostic_label']}",
        f"Total points: {result['total_points']:.6f}",
        "",
        "Prognostic risk calls:",
    ]
    for name, item in result["prognosis_calls"].items():
        lines.append(f"- {name}: {item['label']} (threshold={item['threshold']:.8f})")
    lines.append("")
    lines.append(f"Output directory: {result['output_dir']}")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_prediction(request: PredictionRequest, logger: Callable[[str], None] | None = None) -> dict:
    _log(logger, "Loading model assets and NIfTI image...")
    assets = load_model_assets()
    image = read_wbs_image(request.nii_path)
    bundle = build_render_bundle(image, max_display_height=CANVAS_HEIGHT)

    output_dir = _prepare_output_dir(request.output_root, request.nii_path)
    rendered_png_path = output_dir / "rendered_canvas.png"
    bundle.canvas_image.save(rendered_png_path)
    _save_annotation_preview(bundle, request.circle_display, request.rect_display, output_dir / "annotation_preview.png")

    _log(logger, "Converting ROI C circle annotation into a mask...")
    circle_raw = display_circle_to_raw(request.circle_display, bundle)
    mask_image = build_circle_mask_image(bundle, circle_raw)
    mask_path = output_dir / "roi_c_mask.nii.gz"
    sitk.WriteImage(mask_image, str(mask_path))

    _log(logger, "Extracting 8 selected radiomics features...")
    radiomics_values = extract_selected_radiomics(image, mask_image, assets["selected_radiomics_features"])

    _log(logger, "Preparing deep-learning crop on the rendered WBS canvas...")
    bbox_canvas = display_rect_to_canvas(request.rect_display, bundle)
    deep_feature_path = output_dir / "deep_features.json"

    _log(logger, "Extracting 11 selected deep features...")
    deep_result = run_deep_feature_worker(
        image_path=rendered_png_path,
        bbox=bbox_canvas,
        output_path=deep_feature_path,
    )
    deep_values = deep_result["selected_features"]

    _log(logger, "Standardizing features and computing Radscore...")
    feature_values = {**radiomics_values, **deep_values}
    standardized = standardize_features(feature_values, assets["feature_scaling"])
    radscore = compute_linear_score(
        standardized,
        assets["radscore_model"]["weights"],
        float(assets["radscore_model"].get("intercept", 0.0)),
    )

    _log(logger, "Running diagnostic and prognostic inference...")
    diagnostic_probability = compute_diagnostic_probability(
        age=request.age,
        acquisition_view=request.acquisition_view,
        radscore=radscore,
        model=assets["diagnostic_model"],
    )
    diagnostic_label = classify_probability(diagnostic_probability, threshold=0.5)
    total_points = compute_total_points(
        age=request.age,
        acquisition_view=request.acquisition_view,
        radscore=radscore,
        point_formula=assets["point_formula"],
    )
    prognosis_calls = _build_prognosis_calls(total_points, assets["prognosis_thresholds"])

    result = {
        "input_image": str(request.nii_path),
        "output_dir": str(output_dir),
        "age": float(request.age),
        "acquisition_view": int(request.acquisition_view),
        "radscore": float(radscore),
        "diagnostic_probability": float(diagnostic_probability),
        "diagnostic_label": diagnostic_label,
        "total_points": float(total_points),
        "prognosis_calls": prognosis_calls,
        "radiomics_features": radiomics_values,
        "deep_features": deep_values,
        "standardized_features": standardized,
        "radscore_contributions": compute_radscore_contributions(
            standardized,
            assets["radscore_model"]["weights"],
        ),
        "diagnostic_contributions": compute_diagnostic_contributions(
            age=request.age,
            acquisition_view=request.acquisition_view,
            radscore=radscore,
            model=assets["diagnostic_model"],
        ),
        "bbox_canvas": bbox_canvas,
        "circle_raw": circle_raw,
        "deep_crop_box": deep_result["crop_box"],
        "threshold_notes": {
            "overall_center1_youden": "Use for the overall BM cohort.",
            "solitary_center1_youden": "Prefer this threshold when the patient belongs to the solitary-lesion cohort.",
        },
    }

    summary_path = output_dir / "prediction_summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_text(result, output_dir / "prediction_summary.txt")
    _log(logger, "Prediction finished and outputs were saved.")
    return result
