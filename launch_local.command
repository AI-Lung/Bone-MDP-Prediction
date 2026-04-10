#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/scripts/bootstrap.py"
PROJECT_PYTHON="$SCRIPT_DIR/.runtime/app_env/bin/python"
SYSTEM_PYTHON=""

if [[ -x "$PROJECT_PYTHON" ]]; then
  "$PROJECT_PYTHON" "$BOOTSTRAP_SCRIPT"
  exit $?
fi

if [[ -n "$(command -v python3 2>/dev/null)" ]]; then
  SYSTEM_PYTHON="$(command -v python3)"
elif [[ -n "$(command -v python 2>/dev/null)" ]]; then
  SYSTEM_PYTHON="$(command -v python)"
fi

if [[ -z "$SYSTEM_PYTHON" ]]; then
  echo "Cannot find Python 3.10+."
  echo "Please install Python 3.10 or newer, then double-click this file again."
  echo
  read "reply?Press Enter to close..."
  exit 1
fi

if ! "$SYSTEM_PYTHON" "$BOOTSTRAP_SCRIPT"; then
  echo
  echo "Launch failed. Please review the error above."
  read "reply?Press Enter to close..."
fi
