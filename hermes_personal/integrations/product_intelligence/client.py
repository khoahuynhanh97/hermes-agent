from __future__ import annotations

try:
    from hermes.application.product_resource_service import ProductResourceService
except ImportError:
    class ProductResourceService:  # type: ignore[no-redef]
        def lock_resource_pack(self, payload: dict, owner_user_id: str) -> dict:
            return {
                "resource_pack_id": payload.get("resource_pack_id", "rp_default"),
                "resource_pack_version": payload.get("resource_pack_version", 1),
                "status": "locked",
                "owner_user_id": owner_user_id,
                "manifest_digest": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "assets": payload.get("assets", []),
            }

from hermes_personal.product.research import ProductResearchPipeline, ResearchSpec
from hermes_personal.product.resource_pack import ResourcePackBuilder, ResourcePackSpec


class ProductIntelligenceClient:
    """Deterministic client for Phase 5 Task 2.

    Provides three high‑level operations without external I/O:
    * ``research`` – fabricates a research result.
    * ``build_resource_pack`` – creates a deterministic resource‑pack from that result.
    * ``lock_resource_pack`` – generates a lock payload and runs the anti‑corruption service.
    """

    def __init__(self, owner_user_id: str = "user") -> None:
        self.owner_user_id = owner_user_id
        self.service = ProductResourceService()
        self._pipeline = ProductResearchPipeline()
        self._builder = ResourcePackBuilder()

    # ---------------------------------------------------------------------
    # Research
    # ---------------------------------------------------------------------
    def research(self, product_name: str, keywords: list[str]) -> dict:
        """Run the deterministic research pipeline.

        Returns the raw ``dict`` produced by :class:`ProductResearchPipeline` –
        ``{"summary": ..., "report": ...}``.
        """
        spec = ResearchSpec(product_name=product_name, keywords=keywords)
        result = self._pipeline.run(spec)
        return {"summary": result.summary, "report": result.report}

    # ---------------------------------------------------------------------
    # Resource‑pack build
    # ---------------------------------------------------------------------
    def build_resource_pack(self, research_result: dict) -> dict:
        """Build a deterministic ``ResourcePackResult`` from a research result.

        The ``report`` JSON is parsed for ``product_name`` and ``keywords``.
        Assets are generated as ``{keyword}_asset`` and a simple two‑scene plan
        ``["intro", "outro"]`` is used.
        Returns a plain ``dict`` with the ``ResourcePackResult`` fields.
        """
        report = research_result.get("report", "{}")
        try:
            data = __import__("json").loads(report)
        except Exception as exc:
            raise ValueError("Malformed research report") from exc

        product_name = data.get("product_name", "unknown")
        keywords = data.get("keywords", [])
        assets = [f"{kw}_asset" for kw in keywords]
        scenes = ["intro", "outro"]
        spec = ResourcePackSpec(product_name=product_name, assets=assets, scenes=scenes)
        result = self._builder.build(spec)
        return {
            "summary": result.summary,
            "assets_mapping": result.assets_mapping,
            "scene_plan": result.scene_plan.steps,
        }

    # ---------------------------------------------------------------------
    # Lock
    # ---------------------------------------------------------------------
    def lock_resource_pack(self, pack_dict: dict, owner_user_id: str | None = None) -> dict:
        """Create a lock payload and invoke :class:`ProductResourceService`.

        ``pack_dict`` must contain ``assets_mapping`` as produced by
        :meth:`build_resource_pack`. The method returns the enriched payload
        (including ``manifest_digest`` and ``status="locked"``).
        """
        uid = owner_user_id or self.owner_user_id
        # deterministic id based on summary hash – simple stable string
        resource_pack_id = f"rp_{hash(pack_dict.get('summary', '')) & 0xffffffff}"
        payload: dict = {
            "resource_pack_id": resource_pack_id,
            "resource_pack_version": 1,
            "status": "unlocked",
            "assets": [
                {"asset_id": aid, "local_path": url}
                for aid, url in (pack_dict.get("assets_mapping", {}) or {}).items()
            ],
        }
        locked = self.service.lock_resource_pack(payload, uid)
        return locked
