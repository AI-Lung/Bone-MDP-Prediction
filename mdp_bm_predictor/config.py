from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_PATH = PROJECT_ROOT / "assets" / "model_assets.json"
DEEP_WORKER_SCRIPT = Path(__file__).resolve().parent / "deep_worker.py"
DEFAULT_DL_RUNTIME = "dl_env"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"
WINDOW_TITLE = "MDP Bone Lesion Predictor"
WINDOW_GEOMETRY = "1760x1080"

# The training PNG snapshots used a centered padded canvas rather than the raw
# 512x1024 matrix directly. We recreate that layout for annotation and DL input.
CANVAS_WIDTH = 1422
CANVAS_HEIGHT = 1416
DISPLAY_MAX_HEIGHT = 860
VIEWPORT_WIDTH = 720
VIEWPORT_HEIGHT = 940

# Confirmed clinical mapping from the original model:
# 1 = Anterior, 2 = Posterior.
ACQUISITION_VIEW_OPTIONS = {
    "Anterior (code 1)": 1,
    "Posterior (code 2)": 2,
}

ACQUISITION_VIEW_LABELS = {
    1: "Anterior",
    2: "Posterior",
}
