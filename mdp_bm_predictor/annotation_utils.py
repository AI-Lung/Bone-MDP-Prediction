from __future__ import annotations

from typing import Any

import numpy as np
import SimpleITK as sitk

from .image_utils import RenderBundle


def _last_object(canvas_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not canvas_json:
        return None
    objects = canvas_json.get("objects") or []
    return objects[-1] if objects else None


def extract_rect_annotation(canvas_json: dict[str, Any] | None) -> dict[str, float] | None:
    obj = _last_object(canvas_json)
    if not obj:
        return None
    width = float(obj.get("width", 0.0)) * float(obj.get("scaleX", 1.0))
    height = float(obj.get("height", 0.0)) * float(obj.get("scaleY", 1.0))
    if width <= 0 or height <= 0:
        return None
    return {
        "left": float(obj.get("left", 0.0)),
        "top": float(obj.get("top", 0.0)),
        "width": width,
        "height": height,
    }


def extract_circle_annotation(canvas_json: dict[str, Any] | None) -> dict[str, float] | None:
    obj = _last_object(canvas_json)
    if not obj:
        return None

    scale_x = float(obj.get("scaleX", 1.0))
    scale_y = float(obj.get("scaleY", 1.0))
    if "radius" in obj:
        radius_x = float(obj["radius"]) * scale_x
        radius_y = float(obj["radius"]) * scale_y
    elif "rx" in obj and "ry" in obj:
        radius_x = float(obj["rx"]) * scale_x
        radius_y = float(obj["ry"]) * scale_y
    else:
        radius_x = float(obj.get("width", 0.0)) * scale_x / 2.0
        radius_y = float(obj.get("height", 0.0)) * scale_y / 2.0

    radius = max(radius_x, radius_y)
    if radius <= 0:
        return None

    return {
        "center_x": float(obj.get("left", 0.0)) + radius_x,
        "center_y": float(obj.get("top", 0.0)) + radius_y,
        "radius": radius,
    }


def display_rect_to_canvas(rect: dict[str, float], bundle: RenderBundle) -> dict[str, int]:
    left = rect["left"] / bundle.display_scale
    top = rect["top"] / bundle.display_scale
    width = rect["width"] / bundle.display_scale
    height = rect["height"] / bundle.display_scale

    left = max(0.0, min(left, bundle.canvas_width - 1))
    top = max(0.0, min(top, bundle.canvas_height - 1))
    width = max(1.0, min(width, bundle.canvas_width - left))
    height = max(1.0, min(height, bundle.canvas_height - top))

    return {
        "left": int(round(left)),
        "top": int(round(top)),
        "width": int(round(width)),
        "height": int(round(height)),
    }


def display_circle_to_raw(circle: dict[str, float], bundle: RenderBundle) -> dict[str, float]:
    canvas_center_x = circle["center_x"] / bundle.display_scale
    canvas_center_y = circle["center_y"] / bundle.display_scale
    canvas_radius = circle["radius"] / bundle.display_scale

    raw_center_x = (canvas_center_x - bundle.canvas_offset_x) / bundle.raw_to_canvas_scale
    raw_center_y = (canvas_center_y - bundle.canvas_offset_y) / bundle.raw_to_canvas_scale
    raw_radius = canvas_radius / bundle.raw_to_canvas_scale

    raw_center_x = float(np.clip(raw_center_x, 0, bundle.raw_width - 1))
    raw_center_y = float(np.clip(raw_center_y, 0, bundle.raw_height - 1))
    raw_radius = float(
        np.clip(
            raw_radius,
            1.0,
            max(bundle.raw_width, bundle.raw_height),
        )
    )

    return {
        "center_x": raw_center_x,
        "center_y": raw_center_y,
        "radius": raw_radius,
    }


def build_circle_mask_image(bundle: RenderBundle, circle_raw: dict[str, float]) -> sitk.Image:
    reference_array = sitk.GetArrayFromImage(bundle.image)
    mask = np.zeros_like(reference_array, dtype=np.uint8)

    yy, xx = np.ogrid[: bundle.raw_height, : bundle.raw_width]
    cx = circle_raw["center_x"]
    cy = circle_raw["center_y"]
    radius = circle_raw["radius"]
    circle_mask = ((xx - cx) ** 2 + (yy - cy) ** 2) <= radius**2

    if mask.ndim == 3:
        slice_index = 0 if mask.shape[0] == 1 else mask.shape[0] // 2
        mask[slice_index, :, :] = circle_mask.astype(np.uint8)
    else:
        mask[:, :] = circle_mask.astype(np.uint8)

    mask_image = sitk.GetImageFromArray(mask)
    mask_image.CopyInformation(bundle.image)
    return mask_image

