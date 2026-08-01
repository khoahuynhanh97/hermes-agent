import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes.domain.web_document import WebFetchRequest, WebFetchFailure
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.adapters.web.static_fetcher import StaticWebDocumentFetcher
from hermes.adapters.web.crawl4ai_fetcher import Crawl4AIWebDocumentFetcher, Crawl4AIUnavailable
from hermes.application.web_acquisition_service import WebAcquisitionService


def run_pilot(input_path: Path, output_path: Path):
    if not input_path.is_file():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
    elif isinstance(data, list):
        urls = data
    else:
        print("Error: Input JSON must be a list of URL strings or an object with 'urls' key.", file=sys.stderr)
        sys.exit(1)

    if not (1 <= len(urls) <= 20):
        print(f"Warning: Expected 10-20 URLs, got {len(urls)}.", file=sys.stderr)

    url_policy = PublicWebUrlPolicy()
    static_fetcher = StaticWebDocumentFetcher(policy=url_policy)
    c4a_fetcher = None
    try:
        c4a_fetcher = Crawl4AIWebDocumentFetcher(policy=url_policy)
    except Exception:
        pass

    acquisition_service = WebAcquisitionService(
        static_fetcher=static_fetcher,
        crawl4ai_fetcher=c4a_fetcher,
        enabled=True,
    )

    results = []
    latencies = []

    for index, raw_url in enumerate(urls, start=1):
        req = WebFetchRequest(
            owner_user_id="pilot_user",
            run_id="pilot_run",
            product_id=f"pilot_prod_{index}",
            url=raw_url,
        )

        start_time = time.perf_counter()
        try:
            doc = acquisition_service.acquire(req)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            latencies.append(elapsed_ms)

            results.append({
                "url": doc.final_url,
                "status": "success",
                "code": "ok",
                "acquisition_method": doc.acquisition_method,
                "elapsed_ms": elapsed_ms,
                "html_bytes": len(doc.markdown.encode("utf-8")),  # byte length
                "markdown_chars": len(doc.markdown),
                "warning_count": len(doc.warnings),
                "warnings": list(doc.warnings),
            })
            print(f"[{index}/{len(urls)}] SUCCESS {doc.acquisition_method} in {elapsed_ms}ms: {doc.final_url}")
        except WebFetchFailure as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            latencies.append(elapsed_ms)
            results.append({
                "url": raw_url,
                "status": "failed",
                "code": e.code,
                "detail": e.detail,
                "elapsed_ms": elapsed_ms,
                "html_bytes": 0,
                "markdown_chars": 0,
                "warning_count": 1,
            })
            print(f"[{index}/{len(urls)}] FAILED ({e.code}) in {elapsed_ms}ms: {raw_url}")
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            results.append({
                "url": raw_url,
                "status": "failed",
                "code": "unexpected_error",
                "detail": str(e),
                "elapsed_ms": elapsed_ms,
                "html_bytes": 0,
                "markdown_chars": 0,
                "warning_count": 1,
            })
            print(f"[{index}/{len(urls)}] ERROR in {elapsed_ms}ms: {raw_url} - {e}")

    latencies.sort()
    median_ms = latencies[len(latencies) // 2] if latencies else 0.0

    summary = {
        "total_urls": len(urls),
        "success_count": sum(1 for r in results if r["status"] == "success"),
        "failed_count": sum(1 for r in results if r["status"] == "failed"),
        "static_count": sum(1 for r in results if r.get("acquisition_method") == "static_http"),
        "crawl4ai_count": sum(1 for r in results if r.get("acquisition_method") == "crawl4ai"),
        "median_elapsed_ms": median_ms,
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nPilot report saved to '{output_path}'. Total: {summary['total_urls']}, Success: {summary['success_count']}, Failed: {summary['failed_count']}")


def main():
    parser = argparse.ArgumentParser(description="Hermes Crawl4AI Pilot Tool")
    parser.add_argument("--input", required=True, type=Path, help="Input JSON file containing URLs")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON report file")
    args = parser.parse_args()

    run_pilot(args.input, args.output)


if __name__ == "__main__":
    main()
