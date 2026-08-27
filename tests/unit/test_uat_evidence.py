import json

from companion.settings import Settings
from companion.uat_evidence import configuration_snapshot


def test_configuration_snapshot_redacts_credentials() -> None:
    settings = Settings(
        database_url="sqlite:////tmp/companion.sqlite3",
        groq_api_key="super-secret-groq",
        embedding_api_key="super-secret-embedding",
    )

    serialized = json.dumps(configuration_snapshot(settings))

    assert "super-secret-groq" not in serialized
    assert "super-secret-embedding" not in serialized
    assert serialized.count("present (redacted)") == 2
    assert '"timezone": "Asia/Taipei"' in serialized
    assert '"user_id": "default"' in serialized
    assert '"core_url": "http://127.0.0.1:8000"' in serialized
