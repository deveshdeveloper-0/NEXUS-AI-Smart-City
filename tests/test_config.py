import os
import secrets

from fastapi.testclient import TestClient

from app.config import ENV_FILE, PROJECT_ROOT, load_environment
from app.main import app

client = TestClient(app)


def test_project_root_environment_file_loads_without_overriding_process_values(
    tmp_path,
    monkeypatch,
):
    existing_name = "NEXUS_TEST_EXISTING_VALUE"
    file_name = "NEXUS_TEST_FILE_VALUE"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{existing_name}=from-file\n{file_name}=loaded-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(existing_name, "already-set")
    monkeypatch.delenv(file_name, raising=False)

    load_environment(env_file)

    assert ENV_FILE == PROJECT_ROOT / ".env"
    assert os.environ[existing_name] == "already-set"
    assert os.environ[file_name] == "loaded-from-file"


def test_live_status_never_exposes_configured_secrets(monkeypatch, caplog):
    data_gov_secret = secrets.token_urlsafe(32)
    google_secret = secrets.token_urlsafe(32)
    monkeypatch.setenv("DATA_GOV_API_KEY", data_gov_secret)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", google_secret)

    response = client.get("/api/live/status")

    assert response.status_code == 200
    assert data_gov_secret not in response.text
    assert google_secret not in response.text
    assert data_gov_secret not in caplog.text
    assert google_secret not in caplog.text


def test_frontend_does_not_reference_backend_api_key_variables():
    app_js = (PROJECT_ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "DATA_GOV_API_KEY" not in app_js
    assert "GOOGLE_MAPS_API_KEY" not in app_js
