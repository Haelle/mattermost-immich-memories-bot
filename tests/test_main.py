from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from souvenirs import build_app
from souvenirs.config import Settings


def test_app_built_from_settings_starts_and_authenticates_commands(tmp_path):
    settings = Settings.from_env(
        {
            "IMMICH_URL": "http://127.0.0.1:9",
            "MM_URL": "http://127.0.0.1:9",
            "MM_BOT_TOKEN": "bot-token",
            "MM_COMMAND_TOKENS": "team-token",
            "MASTER_KEY": Fernet.generate_key().decode(),
            "PUBLIC_CALLBACK_URL": "http://souvenirs:8000",
            "DB_PATH": str(tmp_path / "souvenirs.db"),
        }
    )

    with TestClient(build_app(settings)) as client:
        forged = client.post("/command", data={"token": "forged", "user_id": "u1", "text": "statut"})
        genuine = client.post("/command", data={"token": "team-token", "user_id": "u1", "text": "statut"})

    assert forged.status_code == 401
    assert "pas inscrit" in genuine.json()["text"]
