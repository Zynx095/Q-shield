"""Gateway settings, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("DATABASE_URL must start with sqlite:/// (only SQLite is supported)")
    return database_url[len(prefix):] or ":memory:"


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "qshield.db"
    device_offline_timeout_s: float = 15.0
    keys_dir: str = "keys"
    pqc_kem_algorithm: str = "ML-KEM-768"
    pqc_sig_algorithm: str = "ML-DSA-65"
    pqc_enabled: bool = False
    pqc_gateway_kem_key_ids: tuple[str, ...] = ("gateway-kem-1",)  # first = active
    pqc_max_skew_s: float = 300.0
    pqc_session_ttl_s: int = 3600
    require_signed_observations: bool = False
    trust_enabled: bool = True
    trust_config_path: str | None = None
    recovery_tick_s: float = 5.0   # background recovery-deadline timer; 0 disables
    # Optional overrides from the environment; otherwise generated under keys_dir on first use.
    master_key_hex: str | None = field(default=None, repr=False)
    operator_token: str | None = field(default=None, repr=False)
    ingest_token: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, env_file: str | Path | None = ".env") -> "Settings":
        values: dict[str, str | None] = {}
        if env_file and Path(env_file).is_file():
            values.update(dotenv_values(env_file))
        values.update(os.environ)  # real environment wins over .env

        def get(name: str, default: str) -> str:
            v = values.get(name)
            return default if v in (None, "") else str(v)

        return cls(
            host=get("QSHIELD_HOST", cls.host),
            port=int(get("QSHIELD_PORT", str(cls.port))),
            db_path=_sqlite_path(get("DATABASE_URL", "sqlite:///./qshield.db")),
            device_offline_timeout_s=float(
                get("DEVICE_OFFLINE_TIMEOUT_S", str(cls.device_offline_timeout_s))
            ),
            keys_dir=get("KEYS_DIR", cls.keys_dir),
            pqc_kem_algorithm=get("PQC_KEM_ALGORITHM", cls.pqc_kem_algorithm),
            pqc_sig_algorithm=get("PQC_SIG_ALGORITHM", cls.pqc_sig_algorithm),
            pqc_enabled=get("PQC_ENABLED", "true").lower() in ("1", "true", "yes"),
            pqc_gateway_kem_key_ids=tuple(k.strip() for k in get("PQC_GATEWAY_KEM_KEY_IDS", "gateway-kem-1").split(",") if k.strip()),
            pqc_max_skew_s=float(get("PQC_MAX_SKEW_S", str(cls.pqc_max_skew_s))),
            pqc_session_ttl_s=int(get("PQC_SESSION_TTL_S", str(cls.pqc_session_ttl_s))),
            require_signed_observations=get("REQUIRE_SIGNED_OBSERVATIONS", "false").lower() in ("1", "true", "yes"),
            trust_enabled=get("TRUST_ENABLED", "true").lower() in ("1", "true", "yes"),
            trust_config_path=get("TRUST_CONFIG_PATH", "") or None,
            recovery_tick_s=float(get("RECOVERY_TICK_S", str(cls.recovery_tick_s))),
            master_key_hex=get("QSHIELD_MASTER_KEY_HEX", "") or None,
            operator_token=get("QSHIELD_OPERATOR_TOKEN", "") or None,
            ingest_token=get("QSHIELD_INGEST_TOKEN", "") or None,
        )
