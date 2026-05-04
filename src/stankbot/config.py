from __future__ import annotations

import os
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ConfigError(Exception):
    """Raised when the environment is missing required values.

    Carries a human-readable, multi-line message meant to be printed
    directly to stderr — no stack trace, no pydantic noise.
    """


class AppConfig(BaseSettings):
    """Process-level configuration loaded from the environment.

    Per-guild behavior (scoring, templates, channels, roles) lives in the
    database under guild_settings / altars / admin_roles / channel_bindings —
    not here.
    """

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime environment ---
    env: str = "dev"

    # --- Discord ---
    discord_token: SecretStr | None = None
    discord_app_id: int = 1494266000064122930
    owner_id: int | None = None
    owner_default_guild_id: int | None = None
    guild_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/stankbot.db"

    # --- Web ---
    enable_web: bool = True
    web_bind: str = "127.0.0.1:8000"
    web_secret_key: SecretStr | None = None
    oauth_client_secret: SecretStr | None = None
    oauth_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "text"

    # --- Media providers (Maphra) ---
    youtube_api_key: SecretStr | None = None
    spotify_client_id: SecretStr | None = None
    spotify_client_secret: SecretStr | None = None
    spotify_oauth_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"
    spotify_client_token: str | None = None
    spotify_sp_dc: str | None = None

    # --- Dev mocks (ignored unless env == "dev-mock") ---
    mock_discord: bool = False
    mock_auth: bool = False
    mock_auto_events: bool = False
    mock_auto_events_interval: int = 5
    mock_default_user_id: int = 111111111
    mock_default_user_name: str = "DevUser"
    mock_default_guild_id: int | None = None
    mock_default_guild_name: str = "Dev Server"

    @field_validator("guild_ids", mode="before")
    @classmethod
    def _parse_guild_ids(cls, value: object) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        raise TypeError(f"guild_ids: unexpected type {type(value)!r}")

    @field_validator("owner_id", mode="before")
    @classmethod
    def _parse_owner_id(cls, value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)  # type: ignore[arg-type]

    @field_validator("discord_token", mode="before")
    @classmethod
    def _require_token(cls, value: object, info) -> object:  # type: ignore[no-untyped-def]
        # Allow empty token in dev mode with mock Discord.
        data = info.data
        if data.get("env") == "dev-mock" and data.get("mock_discord"):
            if value in (None, ""):
                return "mock-token"
            return value
        if value in (None, ""):
            raise ValueError(
                "DISCORD_TOKEN is empty. Set it in .env.dev from Discord "
                "Developer Portal -> your Application -> Bot -> Reset Token."
            )
        return value

    @model_validator(mode="after")
    def _check_web_config(self) -> AppConfig:
        """If the dashboard is enabled, fail early on missing web secrets."""
        if not self.enable_web:
            return self
        # Skip web secret validation in dev mode when auth is mocked.
        if self.env == "dev-mock" and self.mock_auth:
            return self
        missing: list[str] = []
        if self.web_secret_key is None or not self.web_secret_key.get_secret_value():
            missing.append(
                "WEB_SECRET_KEY (generate: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))")'
            )
        if (
            self.oauth_client_secret is None
            or not self.oauth_client_secret.get_secret_value()
        ):
            missing.append(
                "OAUTH_CLIENT_SECRET (Developer Portal -> OAuth2 -> Reset Secret). "
                "Only needed for dashboard login; set ENABLE_WEB=false to skip."
            )
        if missing:
            lines = "\n  - ".join(missing)
            raise ValueError(
                f"Dashboard is enabled but these env vars are missing:\n  - {lines}"
            )
        return self

    @property
    def default_guild_id(self) -> int:
        if self.owner_default_guild_id is not None:
            return self.owner_default_guild_id
        if self.env == "dev-mock" and self.mock_default_guild_id is not None:
            return self.mock_default_guild_id
        if self.guild_ids:
            return self.guild_ids[0]
        raise ConfigError(
            "No default guild configured. Set OWNER_DEFAULT_GUILD_ID=<guild-id> "
            "in .env.dev (for single-guild dev), or GUILD_IDS=<guild-id> "
            "(comma-separated for multi-guild)."
        )

    @property
    def web_host(self) -> str:
        return self.web_bind.split(":", 1)[0]

    @property
    def web_port(self) -> int:
        host_port = self.web_bind.split(":", 1)
        return int(host_port[1]) if len(host_port) == 2 else 8000


def load_config() -> AppConfig:
    # Load the correct env file based on ENV before pydantic reads the environment.
    env = os.environ.get("ENV", "dev")
    env_file = f".env.{env}"
    if os.path.exists(env_file):
        load_dotenv(env_file, override=False)
    elif os.path.exists(".env.local"):
        # Backward compatibility: old .env.local used for preprod dev.
        load_dotenv(".env.local", override=False)
    if os.path.exists(".env"):
        load_dotenv(".env", override=False)

    try:
        return AppConfig(env=env)
    except Exception as exc:  # noqa: BLE001 - reformat any pydantic failure
        msgs: list[str] = []
        errs = getattr(exc, "errors", None)
        if callable(errs):
            for err in errs():
                field = ".".join(str(p) for p in err.get("loc", ())) or "(config)"
                msg = err.get("msg", str(err))
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, ") :]
                msgs.append(f"{field}: {msg}")
        else:
            msgs.append(str(exc))
        details = "\n  - ".join(msgs)
        raise ConfigError(
            f"Configuration is invalid. Check .env.{env}:\n  - " + details
        ) from None
