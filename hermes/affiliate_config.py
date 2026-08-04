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
    marketplace_crawler_enabled: bool = False
    playwright_crawler_enabled: bool = False
    local_sheet_output_dir: Path = Path("exports/product_research")
    auto_generate_scripts: bool = False

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> AffiliateResearchSettings:
        """Read and validate affiliate settings without logging sensitive values."""
        values = os.environ if environ is None else environ
        google_sheets_enabled = _boolean(values.get("GOOGLE_SHEETS_ENABLED", "0"))
        credentials_file = str(values.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "")).strip()
        spreadsheet_id = str(values.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")).strip()
        if google_sheets_enabled and (not credentials_file or not spreadsheet_id):
            raise ValueError(
                "GOOGLE_SHEETS_ENABLED requires GOOGLE_SHEETS_CREDENTIALS_FILE "
                "and GOOGLE_SHEETS_SPREADSHEET_ID."
            )
        return cls(
            import_directory=_import_directory(values),
            google_sheets_enabled=google_sheets_enabled,
            google_sheets_credentials_file=credentials_file,
            google_sheets_spreadsheet_id=spreadsheet_id,
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
            marketplace_crawler_enabled=_boolean(values.get("HERMES_ENABLE_MARKETPLACE_CRAWLER", "0")),
            playwright_crawler_enabled=_boolean(values.get("HERMES_ENABLE_PLAYWRIGHT_CRAWLER", "0")),
            local_sheet_output_dir=_product_research_output_dir(values),
            auto_generate_scripts=_boolean(values.get("PRODUCT_RESEARCH_AUTO_GENERATE_SCRIPTS", "0")),
        )


def load_affiliate_research_settings(
    environ: Mapping[str, str] | None = None,
) -> AffiliateResearchSettings:
    return AffiliateResearchSettings.from_environment(environ)


def _import_directory(values: Mapping[str, str]) -> Path:
    configured = str(values.get("AFFILIATE_IMPORT_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (load_settings().data_dir / "affiliate_imports").resolve()


def _product_research_output_dir(values: Mapping[str, str]) -> Path:
    configured = str(values.get("PRODUCT_RESEARCH_OUTPUT_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (load_settings().data_dir / "product_research_exports").resolve()


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
