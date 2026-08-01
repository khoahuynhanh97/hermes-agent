from typing import Protocol
from hermes.domain.web_document import WebFetchRequest, WebDocument


class WebDocumentFetcher(Protocol):
    def fetch(self, request: WebFetchRequest) -> WebDocument:
        ...
