import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes.domain.web_document import WebFetchFailure, UnsafeWebUrl
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.adapters.web.static_fetcher import StaticWebDocumentFetcher
from hermes.adapters.web.crawl4ai_fetcher import Crawl4AIWebDocumentFetcher, Crawl4AIUnavailable

MIN_URLS = 10
MAX_URLS = 20
MAX_URLS_PER_HOST = 5
ALLOWED_SOURCE_KINDS = ("manufacturer", "editorial_review", "documentation", "public_article")

_SAFE_DETAILS = {
    "unsafe_url": "URL rejected by security policy",
    "robots_denied": "Blocked by robots.txt",
    "unsupported_content": "Unsupported content type",
    "too_large": "Content exceeds size limit",
    "timeout": "Request timed out",
    "transport_error": "Transport error",
    "render_failed": "Rendering failed",
    "empty_content": "Empty content",
    "unexpected_error": "Unexpected failure",
}


class PilotInputError(Exception):
    """Invalid pilot input (count, duplicates, host limit, source_kind, URL policy)."""


class PilotRuntimeError(Exception):
    """Crawl4AI/Chromium runtime unavailable or crashed. No silent static fallback."""


def redact_url(url: str) -> str:
    """Strip query, fragment, and credentials, keeping scheme://host[:port]/path."""
    parsed = urllib.parse.urlsplit(url)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _safe_detail(code: str) -> str:
    return _SAFE_DETAILS.get(code, "Fetch failed")


def load_entries(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("urls"), list):
        entries = data["urls"]
    elif isinstance(data, list):
        entries = data
    else:
        raise PilotInputError("Input JSON must be a list of objects or an object with a 'urls' list.")

    normalized: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise PilotInputError(f"Entry #{index} must be an object with 'url', 'external_product_id', 'source_kind'.")
        missing = [key for key in ("url", "external_product_id", "source_kind") if not entry.get(key)]
        if missing:
            raise PilotInputError(f"Entry #{index} missing required field(s): {', '.join(missing)}.")
        normalized.append({
            "url": str(entry["url"]),
            "external_product_id": str(entry["external_product_id"]),
            "source_kind": str(entry["source_kind"]),
        })
    return normalized


def validate_batch(
    entries: List[Dict[str, Any]],
    policy: PublicWebUrlPolicy,
) -> List[Dict[str, Any]]:
    if not MIN_URLS <= len(entries) <= MAX_URLS:
        raise PilotInputError(f"Pilot requires {MIN_URLS}-{MAX_URLS} URLs, got {len(entries)}.")

    validated: List[Dict[str, Any]] = []
    seen: set[str] = set()
    host_counts: Dict[str, int] = {}

    for entry in entries:
        source_kind = entry["source_kind"]
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise PilotInputError(
                f"Invalid source_kind '{source_kind}'. Allowed: {', '.join(ALLOWED_SOURCE_KINDS)}."
            )
        try:
            normalized_url = policy.validate(entry["url"])
        except UnsafeWebUrl as exc:
            raise PilotInputError(f"URL rejected by policy: {redact_url(entry['url'])} ({exc.code}).") from exc

        if normalized_url in seen:
            raise PilotInputError(f"Duplicate URL in pilot list: {redact_url(normalized_url)}.")
        seen.add(normalized_url)

        host = (urllib.parse.urlsplit(normalized_url).hostname or "").lower()
        host_counts[host] = host_counts.get(host, 0) + 1
        if host_counts[host] > MAX_URLS_PER_HOST:
            raise PilotInputError(
                f"Host '{host}' exceeds the limit of {MAX_URLS_PER_HOST} URLs per host."
            )

        validated.append({
            "url": normalized_url,
            "external_product_id": entry["external_product_id"],
            "source_kind": source_kind,
        })

    return validated


def _attempt(
    label: str,
    fetcher: Any,
    request: Any,
) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        doc = fetcher.fetch(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "success",
            "code": "ok",
            "elapsed_ms": elapsed_ms,
            "markdown_chars": len(doc.markdown),
            "markdown_bytes": len(doc.markdown.encode("utf-8")),
            "html_bytes": None,  # ponytail: fetchers do not expose raw HTML size; do not fabricate it
            "warning_count": len(doc.warnings),
            "warnings": list(doc.warnings),
            "final_url": redact_url(doc.final_url),
        }
    except Crawl4AIUnavailable:
        raise PilotRuntimeError(
            f"Crawl4AI/Chromium runtime unavailable during {label} fetch; aborting pilot "
            "(no silent static-only fallback)."
        )
    except WebFetchFailure as exc:
        if exc.code == "render_failed":
            raise PilotRuntimeError(
                f"Browser rendering failed during {label} fetch; aborting pilot (no silent static-only fallback)."
            )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "failed",
            "code": exc.code,
            "detail": _safe_detail(exc.code),
            "elapsed_ms": elapsed_ms,
            "markdown_chars": 0,
            "markdown_bytes": 0,
            "html_bytes": None,
            "warning_count": 1,
            "warnings": [],
        }
    except Exception:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "failed",
            "code": "unexpected_error",
            "detail": _safe_detail("unexpected_error"),
            "elapsed_ms": elapsed_ms,
            "markdown_chars": 0,
            "markdown_bytes": 0,
            "html_bytes": None,
            "warning_count": 1,
            "warnings": [],
        }


def _peak_rss_mb() -> Optional[float]:
    try:
        import psutil

        process = psutil.Process()
        samples = [process.memory_info().rss]
        for child in process.children(recursive=True):
            try:
                samples.append(child.memory_info().rss)
            except Exception:
                pass
        return round(max(samples) / (1024 * 1024), 2)
    except Exception:
        return None


def _percentile(values: List[float], index: int) -> float:
    if not values:
        return 0.0
    return values[index]


def run_pilot(
    input_path: Path,
    output_path: Path,
    *,
    policy: Optional[PublicWebUrlPolicy] = None,
    static_fetcher: Any = None,
    crawl4ai_fetcher: Any = None,
) -> Dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise PilotInputError(f"Input file '{input_path}' not found.")

    with open(input_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    policy = policy or PublicWebUrlPolicy()
    entries = load_entries(data)
    entries = validate_batch(entries, policy)

    if static_fetcher is None:
        static_fetcher = StaticWebDocumentFetcher(policy=policy)
    if crawl4ai_fetcher is None:
        _probe_crawl4ai()
        crawl4ai_fetcher = Crawl4AIWebDocumentFetcher(policy=policy)

    results: List[Dict[str, Any]] = []
    latencies: List[float] = []
    peak_rss = _peak_rss_mb()

    for index, entry in enumerate(entries, start=1):
        from hermes.domain.web_document import WebFetchRequest

        request = WebFetchRequest(
            owner_user_id="pilot_user",
            run_id="pilot_run",
            product_id=entry["external_product_id"],
            url=entry["url"],
        )

        static = _attempt("static", static_fetcher, request)
        crawl4ai = _attempt("crawl4ai", crawl4ai_fetcher, request)

        for outcome in (static, crawl4ai):
            latencies.append(outcome["elapsed_ms"])

        static_success = static["status"] == "success"
        crawl4ai_success = crawl4ai["status"] == "success"
        improved = crawl4ai_success and (
            not static_success
            or crawl4ai["markdown_chars"] > static["markdown_chars"]
        )

        results.append({
            "url": redact_url(entry["url"]),
            "external_product_id": entry["external_product_id"],
            "source_kind": entry["source_kind"],
            "static": static,
            "crawl4ai": crawl4ai,
            "crawl4ai_improved": improved,
        })

        print(
            f"[{index}/{len(entries)}] {redact_url(entry['url'])} "
            f"static={static['status']} crawl4ai={crawl4ai['status']} "
            f"improved={improved} ({static['elapsed_ms']:.0f}/{crawl4ai['elapsed_ms']:.0f} ms)"
        )

    latencies.sort()
    median_ms = _percentile(latencies, len(latencies) // 2)
    max_ms = latencies[-1] if latencies else 0.0

    summary: Dict[str, Any] = {
        "status": "ok",
        "total_urls": len(entries),
        "static_success_count": sum(1 for r in results if r["static"]["status"] == "success"),
        "crawl4ai_success_count": sum(1 for r in results if r["crawl4ai"]["status"] == "success"),
        "crawl4ai_improved_count": sum(1 for r in results if r["crawl4ai_improved"]),
        "crawl4ai_not_improved_count": sum(1 for r in results if not r["crawl4ai_improved"]),
        "median_elapsed_ms": median_ms,
        "max_elapsed_ms": max_ms,
        "peak_memory_mb": peak_rss,
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    return summary


def _probe_crawl4ai() -> None:
    try:
        import crawl4ai  # noqa: F401
    except ImportError:
        raise PilotRuntimeError(
            "crawl4ai==0.9.2 is not installed; aborting pilot (no silent static-only fallback)."
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes Crawl4AI Pilot Tool")
    parser.add_argument("--input", required=True, type=Path, help="Input JSON file containing URLs")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON report file")
    args = parser.parse_args(argv)

    try:
        run_pilot(args.input, args.output)
    except (PilotInputError, PilotRuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
