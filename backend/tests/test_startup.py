"""The app entrypoint (app/main.py, auto-detected by Vercel) must explain configuration errors instead of crashing."""

import json
import os
import subprocess
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBE = """
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    for path in ("/", "/api/health"):
        r = c.get(path)
        print(json.dumps({"path": path, "status": r.status_code, "body": r.json()}))
"""


def _run(env_overrides: dict) -> list[dict]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("APP_", "JWT_"))}
    env.update(env_overrides)
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=BACKEND, env=env, capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return [json.loads(line) for line in out.stdout.strip().splitlines()]


def test_entrypoint_serves_app_when_configured():
    rows = _run({"APP_ENV": "staging", "JWT_SECRET": "s" * 48})
    assert rows[0]["status"] == 200 and rows[0]["body"]["health"] == "/api/health"
    assert rows[1]["body"]["status"] == "ok"


def test_entrypoint_reports_bad_configuration_without_secrets():
    secret = "short-secret"
    rows = _run({"APP_ENV": "staging", "JWT_SECRET": secret})
    for row in rows:
        assert row["status"] == 500
        assert "JWT_SECRET" in row["body"]["reason"]
        assert secret not in json.dumps(row["body"])
    rows = _run({"APP_ENV": "Staging", "JWT_SECRET": "s" * 48})
    assert "app_env" in rows[0]["body"]["reason"] and rows[0]["status"] == 500


def test_main_defines_top_level_app_for_vercel_detection():
    """Vercel's build parses app/main.py and requires a module-level `app = ...` statement."""
    import ast

    with open(os.path.join(BACKEND, "app", "main.py")) as f:
        tree = ast.parse(f.read())
    names = {t.id for node in tree.body if isinstance(node, ast.Assign) for t in node.targets if isinstance(t, ast.Name)}
    assert "app" in names
