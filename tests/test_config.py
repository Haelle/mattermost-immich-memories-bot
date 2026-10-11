import pytest

from souvenirs.config import ConfigError, Settings

REQUIRED = {
    "IMMICH_URL": "http://immich_server:2283",
    "MM_URL": "https://mm.example",
    "MM_BOT_TOKEN": "bot-token",
    "MM_COMMAND_TOKENS": "token-a, token-b",
    "MASTER_KEY": "master",
    "PUBLIC_CALLBACK_URL": "http://souvenirs:8000",
}


def test_defaults_apply_when_optional_values_are_missing():
    settings = Settings.from_env(REQUIRED)

    assert settings.check_interval_minutes == 60
    assert settings.command_tokens == {"token-a", "token-b"}
    assert settings.db_path == "/data/souvenirs.db"
    assert settings.link_template == "immich://memory?id={id}"


def test_optional_values_are_read():
    settings = Settings.from_env(REQUIRED | {"CHECK_INTERVAL_MINUTES": "15"})

    assert settings.check_interval_minutes == 15


def test_secret_can_come_from_a_docker_secret_file(tmp_path):
    secret = tmp_path / "master_key"
    secret.write_text("from-file\n")
    env = {key: value for key, value in REQUIRED.items() if key != "MASTER_KEY"}

    settings = Settings.from_env(env | {"MASTER_KEY_FILE": str(secret)})

    assert settings.master_key == "from-file"


def test_missing_required_value_is_reported_by_name():
    env = {key: value for key, value in REQUIRED.items() if key != "MM_BOT_TOKEN"}

    with pytest.raises(ConfigError, match="MM_BOT_TOKEN"):
        Settings.from_env(env)


@pytest.mark.parametrize("interval", ["0", "7", "90", "abc"])
def test_interval_must_divide_an_hour(interval):
    with pytest.raises(ConfigError, match="CHECK_INTERVAL_MINUTES"):
        Settings.from_env(REQUIRED | {"CHECK_INTERVAL_MINUTES": interval})
