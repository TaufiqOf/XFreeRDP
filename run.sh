#!/usr/bin/env bash
# Run XFreeRDP GUI
# Requires: python3, python3-tk
#
# To install the .desktop shortcut so it appears in your app menu:
#   cp xfreerdp-gui.desktop ~/.local/share/applications/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python3"
fi

if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
    echo "ERROR: python3-tk is not installed."
    echo "Install it with:  sudo apt install python3-tk"
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/main.py" "$@"
