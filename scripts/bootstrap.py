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
APP_ENV_DIR = RUNTIME_ROOT / "app_env"
APP_REQUIREMENTS = PROJECT_ROOT / "requirements" / "app.txt"
HEALTHCHECK_SCRIPT = PROJECT_ROOT / "scripts" / "healthcheck.py"
STATE_PATH = RUNTIME_ROOT / "bootstrap_state.json"
BOOTSTRAP_VERSION = "2026.04.08.single-runtime.v1"


def log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    log("Running: " + " ".join(f'"{part}"' if " " in part else part for part in command))
    subprocess.check_call(command, cwd=str(PROJECT_ROOT), env=env)


def read_text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_state() -> dict[str, str]:
    return {
        "bootstrap_version": BOOTSTRAP_VERSION,
        "requirements": read_text_hash(APP_REQUIREMENTS),
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


def install_runtime(python_path: Path) -> None:
    ensure_pip_tooling(python_path)
    run([str(python_path), "-m", "pip", "install", "-r", str(APP_REQUIREMENTS)])


def runtime_needs_sync(desired_state: dict[str, str]) -> bool:
    python_path = venv_python(APP_ENV_DIR)
    if not python_path.exists():
        return True
    return load_saved_state() != desired_state


def run_healthcheck(python_path: Path) -> None:
    run([str(python_path), str(HEALTHCHECK_SCRIPT), "--env", "app"])


def launch_gui(python_path: Path) -> int:
    env = os.environ.copy()
    env["MDP_BM_PREDICTOR_RUNTIME"] = str(python_path)
    command = [str(python_path), str(PROJECT_ROOT / "main.py")]
    log("Launching the predictor GUI...")
    completed = subprocess.run(command, cwd=str(PROJECT_ROOT), env=env)
    return int(completed.returncode)


def main() -> int:
    if sys.version_info < (3, 10):
        log("Python 3.10 or newer is required to set up this project.")
        return 1

    desired_state = compute_state()
    app_python = ensure_venv(APP_ENV_DIR)

    if runtime_needs_sync(desired_state):
        log("Installing or updating required packages...")
        install_runtime(app_python)
        save_state(desired_state)
    else:
        log("Local runtime already matches the current project configuration.")

    log("Running runtime health check...")
    try:
        run_healthcheck(app_python)
    except subprocess.CalledProcessError:
        log("The health check failed. Reinstalling package set once more...")
        install_runtime(app_python)
        run_healthcheck(app_python)
        save_state(desired_state)

    return launch_gui(app_python)


if __name__ == "__main__":
    raise SystemExit(main())
