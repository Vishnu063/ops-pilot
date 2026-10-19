#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python_bin="${OPS_PILOT_PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv || { echo 'Install python3-venv (or the package matching your Python version), then retry.'; exit 1; }
fi
if ! .venv/bin/python -c 'import ops_pilot, triage' >/dev/null 2>&1 || [[ "${1:-}" == "--update" ]]; then
  .venv/bin/python -m pip install -e .
fi
if [[ "${1:-}" == "--update" ]]; then shift; fi
exec .venv/bin/python -m ops_pilot.cli "$@"
