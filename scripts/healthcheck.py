#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def check_img() -> dict[str, str]:
    import tkinter  # noqa: F401

    import PIL
    import SimpleITK
    import numpy
    import radiomics

    project_root = Path(__file__).resolve().parents[1]
    assets_path = project_root / "assets" / "model_assets.json"
    if not assets_path.exists():
        raise FileNotFoundError(f"Missing asset file: {assets_path}")

    return {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "Pillow": PIL.__version__,
        "SimpleITK": SimpleITK.Version_VersionString(),
        "pyradiomics": radiomics.__version__,
        "tkinter": str(getattr(sys.modules.get("tkinter"), "TkVersion", "available")),
    }


def check_dl() -> dict[str, str]:
    import PIL
    import numpy
    import torch
    import torchvision

    return {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "Pillow": PIL.__version__,
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
    }


def check_app() -> dict[str, str]:
    result = check_img()
    result.update(check_dl())
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Health check for the local predictor runtime.")
    parser.add_argument("--env", choices=["app", "img", "dl"], default="app")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env == "img":
        result = check_img()
    elif args.env == "dl":
        result = check_dl()
    else:
        result = check_app()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
