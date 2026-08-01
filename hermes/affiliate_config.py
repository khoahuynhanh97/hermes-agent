from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from hermes.config import load_settings


@dataclass(frozen=True, repr=False)
class AffiliateResearchSettings:
    """Non-secret runtime settings for the affiliate research workflow."""

    import_directory: Path
    google_sheets_enabled: bool
    google_sheets_credentials_file: str = field(repr=False)
    google_sheets_spreadsheet_id: str = field(repr=False)
    shortlist_limit: int = 25
    package_limit: int = 10


def load_affiliate_research_settings(
    environ: Mapping[str, str] | None = None,
) -> AffiliateResearchSettings:
    """Read and validate affiliate settings without logging sensitive values."""
    values = os.environ if environ is None else environ
    import_directory = _import_directory(values)
    return AffiliateResearchSettings(
        import_directory=import_directory,
        google_sheets_enabled=_boolean(values.get("GOOGLE_SHEETS_ENABLED", "0")),
        google_sheets_credentials_file=str(
            values.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
        ).strip(),
        google_sheets_spreadsheet_id=str(
            values.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        ).strip(),
        shortlist_limit=_bounded_integer(
            values.get("AFFILIATE_RESEARCH_SHORTLIST_LIMIT", "25"),
            "AFFILIATE_RESEARCH_SHORTLIST_LIMIT",
            minimum=15,
            maximum=25,
        ),
        package_limit=_bounded_integer(
            values.get("AFFILIATE_RESEARCH_PACKAGE_LIMIT", "10"),
            "AFFILIATE_RESEARCH_PACKAGE_LIMIT",
            minimum=5,
            maximum=10,
        ),
    )


def _import_directory(values: Mapping[str, str]) -> Path:
    configured = str(values.get("AFFILIATE_IMPORT_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (load_settings().data_dir / "affiliate_imports").resolve()


def _boolean(value: object) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("GOOGLE_SHEETS_ENABLED must be a boolean value")


def _bounded_integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed
