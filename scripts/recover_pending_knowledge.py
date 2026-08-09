"""Repair old pending lessons that were created from structured-output fallbacks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.job_watcher import JobWorker
from core.knowledge_store import KB_DIR


RECOVERABLE_SOURCES = {"video_only", "video_and_transcript", "transcript_only", "text_file"}


def build_recovered_entry(
    entry: dict,
    raw_response: str,
    raw_analysis: str,
    analysis_source: str,
    confidence: str,
    worker: JobWorker,
) -> tuple[dict, dict, str]:
    parsed = worker.validate_knowledge_proposal(worker.extract_json_from_response(raw_response))
    repaired_entry = dict(entry)
    repaired_entry.update({
        "title": parsed["title"],
        "category": parsed["category"],
        "hook_type": parsed["hook_type"],
        "cta_style": parsed["cta_style"],
        "voice_tone": parsed["voice_tone"],
        "key_lessons": parsed["key_lessons"],
    })
    repaired_detail = {
        **parsed,
        "validation_status": "recovered_from_raw_response",
        "analysis_source": analysis_source,
        "confidence": confidence,
        "raw_analysis": raw_analysis,
        "needs_review": False,
    }
    report = (
        "# Summary + Analysis\n\n"
        f"## Summary\n\n{parsed['summary']}\n\n"
        f"## Source\n\n- URL/File: {entry.get('source_url', '')}\n"
        f"- Analysis source: {analysis_source}\n"
        f"- Confidence: {confidence}\n\n"
        "## Key Lessons\n\n"
        + "\n".join(f"- {item}" for item in parsed["key_lessons"])
        + f"\n\n## Tools And Concepts\n\n{parsed['tools_and_concepts']}\n"
        + f"\n## Workflow Steps\n\n{parsed['workflow_steps']}\n"
        + f"\n## Hermes Applications\n\n{parsed['hermes_applications']}\n"
        + f"\n## Deep Analysis\n\n{parsed['deep_analysis']}\n"
        + f"\n## Full Analysis\n\n{raw_analysis}\n"
    )
    repaired_detail["summary_analysis"] = report
    return repaired_entry, repaired_detail, report


def build_needs_source_entry(entry: dict, analysis_source: str) -> tuple[dict, dict]:
    repaired_entry = dict(entry)
    repaired_entry["key_lessons"] = [
        "Gửi video gốc, transcript, hoặc file upload để Hermes học nguồn này đáng tin cậy."
    ]
    detail = {
        "validation_status": "needs_source",
        "needs_source": True,
        "analysis_source": analysis_source,
        "summary": "Chưa tạo lesson đáng tin cậy vì chỉ có metadata; cần video, transcript, hoặc file upload.",
        "key_lessons": repaired_entry["key_lessons"],
    }
    return repaired_entry, detail


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _is_placeholder(entry: dict, detail: dict) -> bool:
    summary = str(detail.get("summary") or "").lower()
    return (
        detail.get("validation_status") == "fallback"
        or detail.get("validation_status") == "needs_source"
        or "không thể trích xuất json" in summary
        or "cannot extract json" in summary
    )


def repair_pending_entries(root: Path, dry_run: bool = True) -> dict[str, list[str]]:
    index_path = root / "unified_index.json"
    index = _read_json(index_path)
    worker = JobWorker()
    repaired: list[str] = []
    needs_source: list[str] = []
    skipped: list[str] = []

    for position, entry in enumerate(index.get("entries") or []):
        if entry.get("status") != "pending":
            continue
        detail_path = root / str(entry.get("detail_file") or "")
        if not detail_path.exists():
            continue
        try:
            detail_document = _read_json(detail_path)
        except (OSError, json.JSONDecodeError):
            skipped.append(str(entry.get("id")))
            continue
        detail = detail_document.get("detail") or {}
        if not _is_placeholder(entry, detail):
            continue

        analysis_source = str(detail.get("analysis_source") or "none")
        if analysis_source == "metadata_only":
            repaired_entry, repaired_detail = build_needs_source_entry(entry, analysis_source)
            if not dry_run:
                _write_json(detail_path, {**repaired_entry, "detail": {**detail, **repaired_detail}})
                index["entries"][position] = repaired_entry
            needs_source.append(str(entry.get("id")))
            continue

        if analysis_source not in RECOVERABLE_SOURCES:
            skipped.append(str(entry.get("id")))
            continue

        output_dir = Path(str(entry.get("job_output_dir") or ""))
        raw_path = output_dir / "gemini_raw_response.txt"
        if not raw_path.exists():
            skipped.append(str(entry.get("id")))
            continue
        try:
            repaired_entry, repaired_detail, report = build_recovered_entry(
                entry=entry,
                raw_response=raw_path.read_text(encoding="utf-8-sig"),
                raw_analysis=str(detail.get("raw_analysis") or ""),
                analysis_source=analysis_source,
                confidence=str(detail.get("confidence") or "medium"),
                worker=worker,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            skipped.append(str(entry.get("id")))
            continue

        if not dry_run:
            _write_json(detail_path, {**repaired_entry, "detail": repaired_detail})
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "summary_analysis.md").write_text(report, encoding="utf-8")
            index["entries"][position] = repaired_entry
        repaired.append(str(entry.get("id")))

    if not dry_run:
        _write_json(index_path, index)
    return {"repaired": repaired, "needs_source": needs_source, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=KB_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes; omit for dry-run.")
    args = parser.parse_args()
    result = repair_pending_entries(args.root, dry_run=not args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: repaired={result['repaired']}")
    print(f"{mode}: needs_source={result['needs_source']}")
    print(f"{mode}: skipped={result['skipped']}")


if __name__ == "__main__":
    main()
