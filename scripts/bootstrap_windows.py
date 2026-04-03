#!/usr/bin/env python
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / ".runtime"
IMG_ENV_DIR = RUNTIME_ROOT / "img_env"
DL_ENV_DIR = RUNTIME_ROOT / "dl_env"
IMG_REQUIREMENTS = PROJECT_ROOT / "requirements" / "img.txt"
DL_REQUIREMENTS = PROJECT_ROOT / "requirements" / "dl.txt"
HEALTHCHECK_SCRIPT = PROJECT_ROOT / "scripts" / "healthcheck.py"
STATE_PATH = RUNTIME_ROOT / "bootstrap_state.json"
BOOTSTRAP_VERSION = "2026.04.03.windows-bootstrap.v1"


def log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / "Scripts" / "python.exe"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    log("Running: " + " ".join(f'"{part}"' if " " in part else part for part in command))
    subprocess.check_call(command, cwd=str(PROJECT_ROOT), env=env)


def read_text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_state() -> dict[str, str]:
    return {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "img_requirements": read_text_hash(IMG_REQUIREMENTS),
        "dl_requirements": read_text_hash(DL_REQUIREMENTS),
        "pyproject": read_text_hash(PROJECT_ROOT / "pyproject.toml"),
    }


def load_saved_state() -> dict[str, str] | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_state(state: dict[str, str]) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ensure_venv(venv_dir: Path) -> Path:
    python_path = venv_python(venv_dir)
    if python_path.exists():
        return python_path

    log(f"Creating local runtime: {venv_dir}")
    builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade=False)
    builder.create(str(venv_dir))
    if not python_path.exists():
        raise FileNotFoundError(f"Failed to create python runtime at {python_path}")
    return python_path


def ensure_pip_tooling(python_path: Path) -> None:
    run([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])


def install_img_runtime(python_path: Path) -> None:
    ensure_pip_tooling(python_path)
    run([str(python_path), "-m", "pip", "install", "-r", str(IMG_REQUIREMENTS)])


def install_dl_runtime(python_path: Path) -> None:
    ensure_pip_tooling(python_path)
    run([str(python_path), "-m", "pip", "install", "-r", str(DL_REQUIREMENTS)])


def run_healthcheck(python_path: Path, env_name: str) -> None:
    run([str(python_path), str(HEALTHCHECK_SCRIPT), "--env", env_name])


def runtimes_need_sync(desired_state: dict[str, str]) -> bool:
    img_python = venv_python(IMG_ENV_DIR)
    dl_python = venv_python(DL_ENV_DIR)
    if not img_python.exists() or not dl_python.exists():
        return True
    return load_saved_state() != desired_state


def launch_gui(img_python: Path, dl_python: Path) -> int:
    env = os.environ.copy()
    env["MDP_BM_PREDICTOR_DL_PYTHON"] = str(dl_python)
    command = [str(img_python), str(PROJECT_ROOT / "main.py")]
    log("Launching the predictor GUI...")
    completed = subprocess.run(command, cwd=str(PROJECT_ROOT), env=env)
    return int(completed.returncode)


def main() -> int:
    if os.name != "nt":
        log("This bootstrapper is intended for Windows.")
        return 1

    desired_state = compute_state()
    img_python = ensure_venv(IMG_ENV_DIR)
    dl_python = ensure_venv(DL_ENV_DIR)

    if runtimes_need_sync(desired_state):
        log("Installing or updating required packages...")
        install_img_runtime(img_python)
        install_dl_runtime(dl_python)
        save_state(desired_state)
    else:
        log("Local runtimes already match the current project configuration.")

    log("Running runtime health checks...")
    try:
        run_healthcheck(img_python, "img")
        run_healthcheck(dl_python, "dl")
    except subprocess.CalledProcessError:
        log("A health check failed. Reinstalling package sets once more...")
        install_img_runtime(img_python)
        install_dl_runtime(dl_python)
        run_healthcheck(img_python, "img")
        run_healthcheck(dl_python, "dl")
        save_state(desired_state)

    return launch_gui(img_python, dl_python)


if __name__ == "__main__":
    raise SystemExit(main())
