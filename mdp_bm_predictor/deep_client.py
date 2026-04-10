from __future__ import annotations

import json
from pathlib import Path

from .config import ASSETS_PATH
from .deep_worker import extract_selected_deep_features


def run_deep_feature_worker(
    image_path: str | Path,
    bbox: dict[str, int],
    output_path: str | Path,
    assets_path: str | Path = ASSETS_PATH,
) -> dict:
    result = extract_selected_deep_features(
        image_path=image_path,
        bbox=bbox,
        assets_path=assets_path,
    )
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
