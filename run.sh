#!/usr/bin/env bash
# Start the Menu Price Comparator web UI locally.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate

pip install -q -r requirements.txt
if ! python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  pip install -q playwright
fi
if ! .venv/bin/python -m playwright install --dry-run chromium 2>&1 | grep -q "is already installed"; then
  echo "Installing Playwright Chromium (one-time)..."
  playwright install chromium
fi

export PYTHONPATH=.
echo ""
echo "  Menu Price Comparator"
echo "  Open http://localhost:8501 in your browser"
echo ""
exec streamlit run app_streamlit.py --server.port 8501
