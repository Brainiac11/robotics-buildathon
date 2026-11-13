#!/bin/sh
# Runs a participant app. Extra Python packages listed in requirements.txt are installed into
# the /deps volume, so they are only downloaded once.
set -e
if [ -f requirements.txt ]; then
    stamp="/deps/.installed-$(sha256sum requirements.txt | cut -c1-16)"
    if [ ! -f "$stamp" ]; then
        echo "[app] installing requirements.txt"
        pip install --user --no-warn-script-location -r requirements.txt
        touch "$stamp"
    fi
fi
exec python "${APP_ENTRY:-main.py}" "$@"
