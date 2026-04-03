#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONDA_BIN=""
PROJECT_PYTHON="$SCRIPT_DIR/.runtime/img_env/bin/python"

if [[ -x "$PROJECT_PYTHON" ]]; then
  "$PROJECT_PYTHON" "$SCRIPT_DIR/main.py"
  exit $?
elif [[ -n "${CONDA_EXE:-}" && -x "${CONDA_EXE}" ]]; then
  CONDA_BIN="${CONDA_EXE}"
elif [[ -n "$(command -v conda 2>/dev/null)" ]]; then
  CONDA_BIN="$(command -v conda)"
fi

if [[ -z "$CONDA_BIN" ]]; then
  echo "Cannot find conda. Please open a terminal and run:"
  echo "  conda run -n img_env python \"$SCRIPT_DIR/main.py\""
  echo
  read "reply?Press Enter to close..."
  exit 1
fi

if ! "$CONDA_BIN" run -n img_env python "$SCRIPT_DIR/main.py"; then
  echo
  echo "Launch failed. Please review the error above."
  read "reply?Press Enter to close..."
fi
