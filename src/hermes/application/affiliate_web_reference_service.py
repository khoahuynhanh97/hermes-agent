from typing import Sequence, List, Dict, Any
from hermes.domain.affiliate_research import AffiliateProduct, ReferenceMetadata
from hermes.domain.web_document import WebFetchRequest
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.application.web_acquisition_service import WebAcquisitionService
from hermes.ports.web_document_repository import WebDocumentRepository
from hermes.ports.affiliate_research import AffiliateResearchRepository
from hermes.web_research_config import validate_web_reference_batch, WebResearchSettings, WebBatchRejected


class WebReferenceRejected(Exception):
    """Raised when web reference input is invalid or not allowed for product/owner."""
    pass


ALLOWED_SOURCE_KINDS = {"manufacturer", "editorial_review", "documentation", "public_article"}


class AffiliateWebReferenceService:
    def __init__(
        self,
        web_acquisition_service: WebAcquisitionService,
        web_document_repository: WebDocumentRepository,
        research_repository: AffiliateResearchRepository,
        url_policy: PublicWebUrlPolicy,
        settings: WebResearchSettings = WebResearchSettings(),
    ):
        self.web_acquisition_service = web_acquisition_service
        self.web_document_repository = web_document_repository
        self.research_repository = research_repository
        self.url_policy = url_policy
        self.settings = settings

    def collect(
        self,
        owner_user_id: str,
        run_id: str,
        shortlisted_products: Sequence[AffiliateProduct],
        web_inputs: Sequence[Dict[str, Any]],
    ) -> List[ReferenceMetadata]:
        if not web_inputs:
            return []

        # Map external_product_id -> product
        product_map: Dict[str, AffiliateProduct] = {}
        for product in shortlisted_products:
            if product.owner_user_id != owner_user_id:
                raise WebReferenceRejected(f"Product '{product.id}' owner mismatch.")
            product_map[product.external_product_id] = product

        # Validate inputs & extract URLs
        urls = []
        validated_inputs = []

        for item in web_inputs:
            ext_id = item.get("external_product_id")
            raw_url = item.get("url")
            source_kind = item.get("source_kind", "public_article")

            if not ext_id or ext_id not in product_map:
                raise WebReferenceRejected(f"Product external ID '{ext_id}' is not in shortlist.")

            if source_kind not in ALLOWED_SOURCE_KINDS:
                raise WebReferenceRejected(f"Invalid source_kind '{source_kind}'. Must be one of {ALLOWED_SOURCE_KINDS}.")

            if not raw_url:
                raise WebReferenceRejected("Web reference missing URL.")

            norm_url = self.url_policy.validate(raw_url)
            urls.append(norm_url)
            validated_inputs.append(
                {
                    "product": product_map[ext_id],
                    "raw_url": raw_url,
                    "norm_url": norm_url,
                    "source_kind": source_kind,
                }
            )

        # Validate batch limits
        try:
            validate_web_reference_batch(urls, self.settings)
        except WebBatchRejected as e:
            raise WebReferenceRejected(f"Batch validation failed: {e}") from e

        references: List[ReferenceMetadata] = []

        for entry in validated_inputs:
            product = entry["product"]
            norm_url = entry["norm_url"]
            source_kind = entry["source_kind"]

            # Check reusable document in repository
            doc = self.web_document_repository.find_reusable(owner_user_id, norm_url)
            if doc is None:
                fetch_req = WebFetchRequest(
                    owner_user_id=owner_user_id,
                    run_id=run_id,
                    product_id=product.id,
                    url=norm_url,
                    timeout_seconds=self.settings.timeout_seconds,
                    max_html_bytes=self.settings.max_html_bytes,
                    max_markdown_chars=self.settings.max_markdown_chars,
                )
                doc = self.web_acquisition_service.acquire(fetch_req)
                doc = self.web_document_repository.save(doc)

            # Attach document to run/product
            self.web_document_repository.attach(
                run_id=run_id,
                product_id=product.id,
                document_id=doc.id,
                source_kind=source_kind,
            )

            ref_id = f"ref_web_{doc.id}"
            ref_meta = ReferenceMetadata(
                id=ref_id,
                owner_user_id=owner_user_id,
                product_id=product.id,
                platform="public_web",
                source_url=doc.final_url,
                title=doc.title,
                author_name=doc.metadata.get("author", ""),
                author_url="",
                thumbnail_url="",
                caption=doc.markdown[:200] if doc.markdown else "",
                embed_html="",
                authorization_scope="public_reference",
                rights_status="reference_only",
                media_local_path="",
                collected_at=doc.acquired_at,
                source_type="public_web_document",
                content_hash=doc.content_hash,
            )

            saved_ref = self.research_repository.save_reference(ref_meta)
            references.append(saved_ref)

        return references
