#!/usr/bin/env bash
# Drystone Cobble Street Survey — project setup.
# Installs the Python dependencies, creates the SQLite schema and seeds the
# demo operator plus the sample survey register. It EXITS; it never starts the
# HTTP server (that is `python3 -m app`, run separately).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

echo "==> Upgrading pip/setuptools/wheel"
"$PYTHON" -m pip install --upgrade pip setuptools wheel

echo "==> Installing project dependencies"
"$PYTHON" -m pip install -r requirements.txt

echo "==> Import self-check"
"$PYTHON" -c "import app.main; print('app package imports cleanly')"

echo "==> Creating the schema and seeding demo data (idempotent)"
"$PYTHON" -m app.seed

echo
echo "Setup complete. Start the server with:"
echo '  python3 -m app                       # binds 0.0.0.0:${PORT:-8000}'
echo '  uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"'
echo "The demo operator email is cenius@cenius.ai; its password is shown on the login page."
