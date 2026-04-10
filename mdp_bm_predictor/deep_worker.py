#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract selected deep features from a WBS bbox.")
    parser.add_argument("--image", required=True, help="Rendered PNG path.")
    parser.add_argument("--left", required=True, type=float)
    parser.add_argument("--top", required=True, type=float)
    parser.add_argument("--width", required=True, type=float)
    parser.add_argument("--height", required=True, type=float)
    parser.add_argument("--assets", required=True, help="Model assets JSON path.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    return parser.parse_args()


def load_assets(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_backbone():
    import torch
    import torchvision.models as models

    try:
        weights = models.ResNet101_Weights.DEFAULT
        backbone = models.resnet101(weights=weights)
    except AttributeError:
        backbone = models.resnet101(pretrained=True)
    features_only = torch.nn.Sequential(*list(backbone.children())[:-1])
    features_only.eval()
    return features_only


def clip_bbox(left: float, top: float, width: float, height: float, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    img_width, img_height = image_size
    left = max(0.0, min(left, img_width - 1))
    top = max(0.0, min(top, img_height - 1))
    width = max(1.0, min(width, img_width - left))
    height = max(1.0, min(height, img_height - top))
    return (
        int(round(left)),
        int(round(top)),
        int(round(left + width)),
        int(round(top + height)),
    )


def extract_selected_deep_features(
    image_path: str | Path,
    bbox: dict[str, float],
    assets_path: str | Path,
) -> dict:
    import torch
    import torchvision.transforms as transforms

    assets = load_assets(Path(assets_path))
    selected_features = assets["selected_deep_features"]

    image = Image.open(image_path).convert("RGB")
    crop_box = clip_bbox(
        bbox["left"],
        bbox["top"],
        bbox["width"],
        bbox["height"],
        image.size,
    )
    cropped = image.crop(crop_box)

    transform = transforms.Compose(
        [
            transforms.Resize((512, 512)),
            transforms.ToTensor(),
        ]
    )
    tensor_image = transform(cropped).unsqueeze(0)

    model = load_backbone()
    with torch.no_grad():
        feature_vector = model(tensor_image).view(-1).cpu().numpy()

    selected_values = {
        name: float(feature_vector[int(name[1:]) - 1])
        for name in selected_features
    }

    return {
        "selected_features": selected_values,
        "crop_box": {
            "left": crop_box[0],
            "top": crop_box[1],
            "right": crop_box[2],
            "bottom": crop_box[3],
        },
    }


def main() -> None:
    args = parse_args()
    output = extract_selected_deep_features(
        image_path=args.image,
        bbox={
            "left": args.left,
            "top": args.top,
            "width": args.width,
            "height": args.height,
        },
        assets_path=args.assets,
    )
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
