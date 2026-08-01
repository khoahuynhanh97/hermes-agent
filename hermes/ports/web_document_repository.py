from typing import Protocol, Optional, List
from hermes.domain.web_document import WebDocument


class WebDocumentRepository(Protocol):
    def find_reusable(
        self, owner_user_id: str, normalized_url: str
    ) -> Optional[WebDocument]:
        ...

    def save(self, document: WebDocument) -> WebDocument:
        ...

    def attach(
        self, run_id: str, product_id: str, document_id: str, source_kind: str
    ) -> None:
        ...

    def list_for_product(
        self, owner_user_id: str, run_id: str, product_id: str
    ) -> List[WebDocument]:
        ...
