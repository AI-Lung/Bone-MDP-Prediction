from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from PIL import Image

from .config import CANVAS_HEIGHT, CANVAS_WIDTH, DISPLAY_MAX_HEIGHT


@dataclass
class RenderBundle:
    image: sitk.Image
    raw_array: np.ndarray
    canvas_image: Image.Image
    display_image: Image.Image
    raw_width: int
    raw_height: int
    canvas_width: int
    canvas_height: int
    raw_to_canvas_scale: float
    canvas_offset_x: float
    canvas_offset_y: float
    display_scale: float

    @property
    def display_width(self) -> int:
        return self.display_image.width

    @property
    def display_height(self) -> int:
        return self.display_image.height


def read_wbs_image(file_path: str | Path) -> sitk.Image:
    return sitk.ReadImage(str(file_path))


def write_uploaded_file(uploaded_file, output_path: Path) -> Path:
    output_path.write_bytes(uploaded_file.getbuffer())
    return output_path


def extract_2d_slice(image: sitk.Image) -> np.ndarray:
    array = sitk.GetArrayFromImage(image)
    if array.ndim == 3:
        if array.shape[0] == 1:
            return np.asarray(array[0], dtype=np.float32)
        return np.asarray(array[array.shape[0] // 2], dtype=np.float32)
    if array.ndim == 2:
        return np.asarray(array, dtype=np.float32)
    raise ValueError(f"Unsupported image shape: {array.shape}")


def normalize_to_uint8(raw_array: np.ndarray) -> np.ndarray:
    array = np.nan_to_num(raw_array, nan=0.0, posinf=0.0, neginf=0.0)
    low = float(np.min(array))
    high = float(np.percentile(array, 99.5))
    if high <= low:
        high = float(np.max(array))
    if high <= low:
        return np.zeros_like(array, dtype=np.uint8)
    clipped = np.clip(array, low, high)
    scaled = ((clipped - low) / (high - low) * 255.0).astype(np.uint8)
    return scaled


def build_render_bundle(
    image: sitk.Image,
    canvas_width: int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
    max_display_height: int = DISPLAY_MAX_HEIGHT,
) -> RenderBundle:
    raw_array = extract_2d_slice(image)
    raw_height, raw_width = raw_array.shape
    grayscale = Image.fromarray(normalize_to_uint8(raw_array), mode="L").convert("RGB")

    raw_to_canvas_scale = canvas_height / raw_height
    resized_width = max(1, int(round(raw_width * raw_to_canvas_scale)))
    resized = grayscale.resize((resized_width, canvas_height), Image.Resampling.BILINEAR)

    canvas = Image.new("RGB", (canvas_width, canvas_height), color=(0, 0, 0))
    offset_x = (canvas_width - resized_width) / 2.0
    offset_y = 0.0
    canvas.paste(resized, (int(round(offset_x)), int(round(offset_y))))

    display_scale = min(1.0, max_display_height / canvas_height)
    display_size = (
        max(1, int(round(canvas_width * display_scale))),
        max(1, int(round(canvas_height * display_scale))),
    )
    display_image = canvas.resize(display_size, Image.Resampling.BILINEAR)

    return RenderBundle(
        image=image,
        raw_array=raw_array,
        canvas_image=canvas,
        display_image=display_image,
        raw_width=raw_width,
        raw_height=raw_height,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        raw_to_canvas_scale=raw_to_canvas_scale,
        canvas_offset_x=offset_x,
        canvas_offset_y=offset_y,
        display_scale=display_scale,
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

