"""Configuration loading for GridGuard.

Configuration is read from a TOML file: the standard-library ``tomllib`` on
Python 3.11+, or the ``tomli`` backport on Python 3.10. Either way the
config layer adds no third-party dependency on modern interpreters.
Everything has a default, so GridGuard works with no config file at all.

Lookup order for the config file:

1. an explicit ``--config PATH`` (handled by the CLI),
2. ``./gridguard.toml`` in the current directory,
3. ``~/.config/gridguard/config.toml``.

Example ``gridguard.toml``::

    zone = "IESCO-F7-1"
    schedule = "examples/iesco-f7.json"
    database = "~/.local/share/gridguard/history.db"
    safety_factor = 1.25
    percentile = 90
    min_samples = 3
    fallback_seconds = 120

    [durations]            # known starting estimates, in seconds
    "docker build" = 600
    "git push" = 45
    "alembic upgrade" = 90
"""

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: stdlib tomllib arrived in 3.11
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SAFETY_FACTOR = 1.25
DEFAULT_PERCENTILE = 90.0
DEFAULT_MIN_SAMPLES = 3
DEFAULT_FALLBACK_SECONDS = 120.0
DEFAULT_HORIZON_DAYS = 14


class ConfigError(Exception):
    """Raised for a missing or invalid configuration file."""


def _expand(path: str | None) -> Path | None:
    if not path:
        return None
    return Path(path).expanduser()


@dataclass(slots=True)
class Config:
    zone: str = "DEFAULT"
    schedule_path: Path | None = None
    database_path: Path = field(
        default_factory=lambda: Path("~/.local/share/gridguard/history.db").expanduser()
    )
    safety_factor: float = DEFAULT_SAFETY_FACTOR
    percentile: float = DEFAULT_PERCENTILE
    min_samples: int = DEFAULT_MIN_SAMPLES
    fallback_seconds: float = DEFAULT_FALLBACK_SECONDS
    horizon_days: int = DEFAULT_HORIZON_DAYS
    durations: dict[str, float] = field(default_factory=dict)
    source_path: Path | None = None

    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict, *, source_path: Path | None = None) -> "Config":
        durations = {str(k): float(v) for k, v in (data.get("durations") or {}).items()}
        return cls(
            zone=str(data.get("zone", "DEFAULT")),
            schedule_path=_expand(data.get("schedule")),
            database_path=_expand(data.get("database")) or cls().database_path,
            safety_factor=float(data.get("safety_factor", DEFAULT_SAFETY_FACTOR)),
            percentile=float(data.get("percentile", DEFAULT_PERCENTILE)),
            min_samples=int(data.get("min_samples", DEFAULT_MIN_SAMPLES)),
            fallback_seconds=float(
                data.get("fallback_seconds", DEFAULT_FALLBACK_SECONDS)
            ),
            horizon_days=int(data.get("horizon_days", DEFAULT_HORIZON_DAYS)),
            durations=durations,
            source_path=source_path,
        )

    @classmethod
    def load(cls, explicit_path: str | Path | None = None) -> "Config":
        candidates: list[Path] = []
        if explicit_path:
            candidates.append(Path(explicit_path).expanduser())
        else:
            candidates.append(Path("gridguard.toml"))
            candidates.append(Path("~/.config/gridguard/config.toml").expanduser())

        for path in candidates:
            if path.is_file():
                try:
                    with path.open("rb") as fh:
                        data = tomllib.load(fh)
                except tomllib.TOMLDecodeError as exc:
                    raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
                except OSError as exc:
                    raise ConfigError(f"cannot read config file {path}: {exc}") from exc
                return cls.from_dict(data, source_path=path)

        if explicit_path:
            raise ConfigError(f"config file not found: {explicit_path}")
        return cls()  # all defaults
