from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_in_file_manager(path: str | Path) -> None:
    target = Path(path).expanduser().resolve()
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
        return
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(target)])
