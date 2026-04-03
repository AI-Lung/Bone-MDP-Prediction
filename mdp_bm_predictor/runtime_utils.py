from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def venv_python_path(venv_dir: str | Path) -> Path:
    venv_dir = Path(venv_dir)
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def find_project_runtime_python(env_name: str) -> str | None:
    candidate = venv_python_path(project_root() / ".runtime" / env_name)
    if candidate.exists():
        return str(candidate)
    return None


def _discover_conda_roots() -> list[Path]:
    roots: list[Path] = []

    conda_exe_env = os.environ.get("CONDA_EXE", "").strip()
    if conda_exe_env:
        conda_exe_path = Path(conda_exe_env).expanduser()
        if conda_exe_path.exists() and len(conda_exe_path.parents) >= 2:
            roots.append(conda_exe_path.parents[1])

    conda_prefix_env = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix_env:
        conda_prefix = Path(conda_prefix_env).expanduser()
        for parent in conda_prefix.parents:
            if parent.name == "envs":
                roots.append(parent.parent)
                break

    mamba_root_env = os.environ.get("MAMBA_ROOT_PREFIX", "").strip()
    if mamba_root_env:
        roots.append(Path(mamba_root_env).expanduser())

    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    program_data = os.environ.get("PROGRAMDATA", "").strip()
    known_names = ["miniconda3", "anaconda3", "mambaforge", "miniforge3"]

    for name in known_names:
        roots.append(home / name)
        if local_app_data:
            roots.append(Path(local_app_data) / name)
        if program_data:
            roots.append(Path(program_data) / name)

    seen: set[str] = set()
    unique_roots: list[Path] = []
    for root in roots:
        root_str = str(root)
        if root_str in seen:
            continue
        seen.add(root_str)
        unique_roots.append(root)
    return unique_roots


def guess_python_for_env(env_name: str) -> str | None:
    candidates: list[Path] = []
    current_python = Path(sys.executable).resolve()
    for parent in current_python.parents:
        if parent.name == "envs":
            candidates.append(venv_python_path(parent / env_name))

    for root in _discover_conda_roots():
        candidates.append(venv_python_path(root / "envs" / env_name))

    seen: set[str] = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        if candidate.exists():
            return candidate_str
    return None


def find_conda_executable() -> str | None:
    candidates = [
        shutil.which("conda"),
        shutil.which("conda.exe"),
        os.environ.get("CONDA_EXE", "").strip() or None,
    ]

    for root in _discover_conda_roots():
        candidates.append(str(root / "bin" / "conda"))
        candidates.append(str(root / "Scripts" / "conda.exe"))

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def suggest_default_dl_runtime() -> str:
    env_value = os.environ.get("MDP_BM_PREDICTOR_DL_PYTHON", "").strip()
    if env_value and Path(env_value).expanduser().exists():
        return env_value

    project_runtime = find_project_runtime_python("dl_env")
    if project_runtime:
        return project_runtime

    guessed_runtime = guess_python_for_env("dl_env")
    if guessed_runtime:
        return guessed_runtime

    return "dl_env"


def resolve_runtime_launcher(runtime_spec: str | Path) -> list[str]:
    runtime_text = str(runtime_spec).strip()
    if not runtime_text:
        raise ValueError("Deep learning runtime is empty.")

    runtime_path = Path(runtime_text).expanduser()
    if runtime_path.exists():
        return [str(runtime_path)]

    guessed_python = guess_python_for_env(runtime_text)
    if guessed_python:
        return [guessed_python]

    project_runtime = find_project_runtime_python(runtime_text)
    if project_runtime:
        return [project_runtime]

    conda_executable = find_conda_executable()
    if conda_executable:
        return [conda_executable, "run", "-n", runtime_text, "python"]

    raise FileNotFoundError(
        f"Cannot resolve deep-learning runtime '{runtime_text}'. "
        "Please provide a valid python path or a conda environment name."
    )


def open_in_file_manager(path: str | Path) -> None:
    target = Path(path).expanduser().resolve()
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
        return
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(target)])
