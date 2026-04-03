import json
from functools import lru_cache

from .config import ASSETS_PATH


@lru_cache(maxsize=1)
def load_model_assets() -> dict:
    with ASSETS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)

