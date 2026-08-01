import datetime
import uuid
import requests
from typing import Optional
from hermes.domain.web_document import (
    WebFetchRequest,
    WebDocument,
    WebFetchFailure,
    UnsafeWebUrl,
)
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.application.web_document_normalizer import WebDocumentNormalizer

DEFAULT_USER_AGENT = "HermesAgent/1.0 (WebAcquisition)"


class StaticWebDocumentFetcher:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        policy: Optional[PublicWebUrlPolicy] = None,
        normalizer: Optional[WebDocumentNormalizer] = None,
    ):
        self.session = session or requests.Session()
        self.policy = policy or PublicWebUrlPolicy()
        self.normalizer = normalizer or WebDocumentNormalizer()

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        current_url = self.policy.validate(request.url)
        redirect_count = 0
        max_redirects = 5

        headers = {"User-Agent": DEFAULT_USER_AGENT}

        while True:
            try:
                resp = self.session.get(
                    current_url,
                    allow_redirects=False,
                    stream=True,
                    timeout=request.timeout_seconds,
                    headers=headers,
                )
            except requests.Timeout as e:
                raise WebFetchFailure("Request timed out", code="timeout", retryable=True) from e
            except requests.RequestException as e:
                raise WebFetchFailure(f"Transport error: {e}", code="transport_error", retryable=True) from e

            # Handle redirects
            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise WebFetchFailure("Too many redirects (max 5)", code="transport_error", retryable=True)

                location = resp.headers.get("Location")
                if not location:
                    raise WebFetchFailure("Redirect response missing Location header", code="transport_error", retryable=True)

                # Re-validate redirect target via policy
                current_url = self.policy.validate_redirect(current_url, location)
                continue

            if resp.status_code != 200:
                retryable = resp.status_code >= 500
                raise WebFetchFailure(
                    f"HTTP response error status {resp.status_code}",
                    code="transport_error",
                    retryable=retryable,
                )

            # Validate Content-Type
            content_type = resp.headers.get("Content-Type", "").lower()
            if not any(allowed in content_type for allowed in ("text/html", "application/xhtml+xml")):
                raise WebFetchFailure(
                    f"Unsupported content type '{content_type}'",
                    code="unsupported_content",
                    retryable=False,
                )

            # Read content up to max_html_bytes
            html_chunks = []
            downloaded_bytes = 0

            if hasattr(resp, "iter_content"):
                chunks = resp.iter_content(chunk_size=8192)
            else:
                chunks = [getattr(resp, "content", b"")]

            for chunk in chunks:
                if not chunk:
                    continue
                downloaded_bytes += len(chunk)
                if downloaded_bytes > request.max_html_bytes:
                    raise WebFetchFailure(
                        f"HTML content size exceeds max allowed limit ({request.max_html_bytes} bytes)",
                        code="too_large",
                        retryable=False,
                    )
                html_chunks.append(chunk)

            raw_bytes = b"".join(html_chunks)
            try:
                html_text = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                html_text = raw_bytes.decode("latin-1", errors="replace")

            # Normalize document
            norm_res = self.normalizer.normalize(
                html_text,
                base_url=current_url,
                max_markdown_chars=request.max_markdown_chars,
            )

            doc_id = f"doc_{uuid.uuid4().hex[:16]}"
            acquired_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

            return WebDocument(
                id=doc_id,
                owner_user_id=request.owner_user_id,
                run_id=request.run_id,
                product_id=request.product_id,
                requested_url=request.url,
                final_url=current_url,
                title=norm_res.title,
                markdown=norm_res.markdown,
                metadata=norm_res.metadata,
                acquisition_method="static_http",
                content_hash=norm_res.content_hash,
                rights_status="reference_only",
                warnings=norm_res.warnings,
                acquired_at=acquired_at,
            )
