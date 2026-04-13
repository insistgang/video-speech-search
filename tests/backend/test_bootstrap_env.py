from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"


def test_importing_backend_main_reads_api_key_and_allowed_dirs_from_env_file(tmp_path):
    allowed_a = tmp_path / "allowed-a"
    allowed_b = tmp_path / "allowed-b"
    allowed_a.mkdir()
    allowed_b.mkdir()

    original_env = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else None
    ENV_PATH.write_text(
        "\n".join(
            [
                "API_KEY=from-env-file",
                f"ALLOWED_VIDEO_DIRS={allowed_a}{os.pathsep}{allowed_b}",
                "FINE_SCAN_MODE=frame",
            ]
        ),
        encoding="utf-8",
    )

    try:
        child_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"API_KEY", "ALLOWED_VIDEO_DIRS", "FINE_SCAN_MODE"}
        }
        child_env["PYTHONPATH"] = str(ROOT)
        completed = subprocess.run(
            [
                "python",
                "-c",
                (
                    "import json; import backend.main; "
                    "from backend.auth import get_api_key; "
                    "from backend.models import get_allowed_video_directories; "
                    "print(json.dumps({'api_key': get_api_key(), "
                    "'allowed_dirs': [str(path) for path in get_allowed_video_directories()]}))"
                ),
            ],
            cwd=str(ROOT),
            env=child_env,
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        if original_env is None:
            ENV_PATH.unlink(missing_ok=True)
        else:
            ENV_PATH.write_text(original_env, encoding="utf-8")

    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["api_key"] == "from-env-file"
    assert payload["allowed_dirs"] == [str(allowed_a.resolve()), str(allowed_b.resolve())]
