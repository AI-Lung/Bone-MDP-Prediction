from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from PIL import Image

from .config import CANVAS_HEIGHT, CANVAS_WIDTH, DISPLAY_MAX_HEIGHT


@dataclass
class RenderBundle:
    image: sitk.Image | None
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


@dataclass(frozen=True)
class DisplayWindow:
    center: float
    width: float
    level_min: float
    level_max: float
    width_min: float
    width_max: float


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


def _sanitize_array(raw_array: np.ndarray) -> np.ndarray:
    return np.nan_to_num(np.asarray(raw_array, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def default_intensity_limits(raw_array: np.ndarray) -> tuple[float, float]:
    array = _sanitize_array(raw_array)
    low = float(np.min(array))
    high = float(np.percentile(array, 99.5))
    if high <= low:
        high = float(np.max(array))
    if high <= low:
        high = low + 1.0
    return low, high


def describe_display_window(raw_array: np.ndarray) -> DisplayWindow:
    array = _sanitize_array(raw_array)
    data_min = float(np.min(array))
    data_max = float(np.max(array))
    default_low, default_high = default_intensity_limits(array)
    width = max(default_high - default_low, 1.0)
    center = (default_low + default_high) / 2.0
    dynamic_span = max(data_max - data_min, width)
    level_padding = max(width * 0.6, dynamic_span * 0.1, 1.0)
    level_min = min(data_min, center - level_padding)
    level_max = max(data_max, center + level_padding)
    width_min = max(width * 0.1, dynamic_span * 0.02, 1.0)
    width_max = max(width * 3.0, dynamic_span, width_min + 1.0)
    return DisplayWindow(
        center=center,
        width=width,
        level_min=level_min,
        level_max=level_max,
        width_min=width_min,
        width_max=width_max,
    )


def normalize_to_uint8(
    raw_array: np.ndarray,
    *,
    window_center: float | None = None,
    window_width: float | None = None,
) -> np.ndarray:
    array = _sanitize_array(raw_array)
    if window_center is None or window_width is None:
        low, high = default_intensity_limits(array)
    else:
        width = max(float(window_width), 1.0)
        center = float(window_center)
        low = center - width / 2.0
        high = center + width / 2.0
    if high <= low:
        return np.zeros_like(array, dtype=np.uint8)
    clipped = np.clip(array, low, high)
    scaled = ((clipped - low) / (high - low) * 255.0).astype(np.uint8)
    return scaled


def build_render_bundle_from_array(
    raw_array: np.ndarray,
    *,
    image: sitk.Image | None = None,
    canvas_width: int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
    max_display_height: int = DISPLAY_MAX_HEIGHT,
    window_center: float | None = None,
    window_width: float | None = None,
) -> RenderBundle:
    raw_array = _sanitize_array(raw_array)
    raw_height, raw_width = raw_array.shape
    grayscale = Image.fromarray(
        normalize_to_uint8(raw_array, window_center=window_center, window_width=window_width),
        mode="L",
    ).convert("RGB")

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


def build_render_bundle(
    image: sitk.Image,
    canvas_width: int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
    max_display_height: int = DISPLAY_MAX_HEIGHT,
    window_center: float | None = None,
    window_width: float | None = None,
) -> RenderBundle:
    raw_array = extract_2d_slice(image)
    return build_render_bundle_from_array(
        raw_array,
        image=image,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        max_display_height=max_display_height,
        window_center=window_center,
        window_width=window_width,
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
