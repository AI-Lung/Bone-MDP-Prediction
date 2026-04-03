from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import ASSETS_PATH, DEEP_WORKER_SCRIPT
from .runtime_utils import resolve_runtime_launcher


def run_deep_feature_worker(
    runtime_spec: str | Path,
    image_path: str | Path,
    bbox: dict[str, int],
    output_path: str | Path,
    assets_path: str | Path = ASSETS_PATH,
    worker_script: str | Path = DEEP_WORKER_SCRIPT,
) -> dict:
    command = [
        *resolve_runtime_launcher(runtime_spec),
        str(worker_script),
        "--image",
        str(image_path),
        "--left",
        str(bbox["left"]),
        "--top",
        str(bbox["top"]),
        "--width",
        str(bbox["width"]),
        "--height",
        str(bbox["height"]),
        "--assets",
        str(assets_path),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown dl worker error"
        raise RuntimeError(detail)
    with Path(output_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
