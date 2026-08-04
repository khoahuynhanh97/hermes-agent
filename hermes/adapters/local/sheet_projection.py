from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from hermes.domain.affiliate_research import ProjectionResult


class LocalSheetProjection:
    _TABS = {
        "Products": "Products.csv",
        "Shortlist": "Shortlist.csv",
        "Scripts": "Scripts.csv",
        "Runs_Errors": "Runs_Errors.csv",
    }

    def __init__(self, repository: Any, output_root: str | Path):
        self._repository = repository
        self._output_root = Path(output_root).expanduser().resolve()

    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        try:
            payloads = self._payloads(self._repository.projection_rows(owner_user_id, run_id))
            run_dir = self._run_dir(owner_user_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            for tab_name, filename in self._TABS.items():
                self._write_csv(run_dir / filename, payloads.get(tab_name, []))
            self._write_xlsx_if_available(run_dir, payloads)
        except Exception as error:
            return ProjectionResult(ok=False, retryable=True, detail=_redact(str(error))[:1000])
        return ProjectionResult(ok=True, retryable=False, detail=str(self._run_dir(owner_user_id, run_id)))

    def output_paths(self, owner_user_id: str, run_id: str) -> dict[str, str]:
        run_dir = self._run_dir(owner_user_id, run_id)
        paths = {tab: str((run_dir / filename).resolve()) for tab, filename in self._TABS.items()}
        xlsx = run_dir / "product_research_run.xlsx"
        if xlsx.exists():
            paths["Workbook"] = str(xlsx.resolve())
        return paths

    def _run_dir(self, owner_user_id: str, run_id: str) -> Path:
        return self._output_root / _safe_segment(owner_user_id) / _safe_segment(run_id)

    def _payloads(self, rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
        products = rows.get("products", [])
        return {
            "Products": products,
            "Shortlist": [row for row in products if row.get("eligibility_status") == "shortlisted"],
            "Scripts": rows.get("packages", []),
            "Runs_Errors": rows.get("runs", []),
        }

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        header = ["stable_id", *sorted({key for row in rows for key in row if key != "id"})]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in rows:
                stable_id = str(row.get("id", ""))
                writer.writerow([stable_id, *[_cell(row.get(column)) for column in header[1:]]])

    @staticmethod
    def _write_xlsx_if_available(run_dir: Path, payloads: dict[str, list[dict]]) -> None:
        try:
            from openpyxl import Workbook
        except ImportError:
            return
        workbook = Workbook()
        default = workbook.active
        workbook.remove(default)
        for tab_name, rows in payloads.items():
            sheet = workbook.create_sheet(tab_name)
            header = ["stable_id", *sorted({key for row in rows for key in row if key != "id"})]
            sheet.append(header)
            for row in rows:
                sheet.append([str(row.get("id", "")), *[_cell(row.get(column)) for column in header[1:]]])
        workbook.save(run_dir / "product_research_run.xlsx")


def _cell(value: Any) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return "" if value is None else value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return segment.strip("._") or "unknown"


def _redact(value: str) -> str:
    return re.sub(r"(?i)(secret|token|api[_-]?key|password)[^\s,;]*", "[redacted]", value)