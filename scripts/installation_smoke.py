"""Exercise the installed CLI/wizard without Docker or a real customer target."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    with tempfile.TemporaryDirectory() as root:
        config = Path(root) / "config.json"
        base = [sys.executable, "-m", "ops_pilot.cli", "setup", "--config", str(config)]
        first = subprocess.run(base, input="Demo application\ndefault\nowned-disposable-app\nhttp://127.0.0.1:8080/health\n",
                               text=True, capture_output=True, timeout=15, cwd=root)
        assert first.returncode == 0, first.stdout + first.stderr
        original = config.read_bytes()
        assert json.loads(original)["container"] == "owned-disposable-app"
        assert config.stat().st_mode & 0o777 == 0o600
        cancelled = subprocess.run(base, input="cancel\n", text=True, capture_output=True, timeout=15, cwd=root)
        assert cancelled.returncode == 1
        assert config.read_bytes() == original, "Cancelled setup changed the existing configuration"
        help_result = subprocess.run(["ops-pilot", "--help"], text=True, capture_output=True, timeout=15, cwd=root)
        assert help_result.returncode == 0, help_result.stderr
        assert "--ai-model" in help_result.stdout
    print("Installed CLI and setup smoke passed: config creation, private mode, cancellation and command entry point.")


if __name__ == "__main__":
    main()
