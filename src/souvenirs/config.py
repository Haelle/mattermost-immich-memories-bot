from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


def _value(env: Mapping[str, str], name: str, default: str | None = None) -> str:
    if f"{name}_FILE" in env:
        return Path(env[f"{name}_FILE"]).read_text().strip()
    if name in env:
        return env[name]
    if default is None:
        raise ConfigError(f"Missing required setting {name} (or {name}_FILE)")
    return default


def _check_interval(env: Mapping[str, str]) -> int:
    value = _value(env, "CHECK_INTERVAL_MINUTES", "60")
    if not value.isdigit() or int(value) == 0 or 60 % int(value):
        raise ConfigError(f"CHECK_INTERVAL_MINUTES must divide 60 (1, 5, 15, 30, 60…), got {value!r}")
    return int(value)


@dataclass(frozen=True)
class Settings:
    immich_url: str
    mm_url: str
    mm_bot_token: str
    command_tokens: set[str]
    master_key: str
    callback_url: str
    db_path: str
    link_template: str
    check_interval_minutes: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        return cls(
            immich_url=_value(env, "IMMICH_URL"),
            mm_url=_value(env, "MM_URL"),
            mm_bot_token=_value(env, "MM_BOT_TOKEN"),
            command_tokens={token.strip() for token in _value(env, "MM_COMMAND_TOKENS").split(",") if token.strip()},
            master_key=_value(env, "MASTER_KEY"),
            callback_url=_value(env, "PUBLIC_CALLBACK_URL"),
            db_path=_value(env, "DB_PATH", "/data/souvenirs.db"),
            link_template=_value(env, "LINK_TEMPLATE", "immich://memory?id={id}"),
            check_interval_minutes=_check_interval(env),
        )
