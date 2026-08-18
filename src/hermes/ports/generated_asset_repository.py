from __future__ import annotations

from typing import Protocol, Optional
from hermes.domain.generated_asset import GeneratedAsset


class GeneratedAssetRepository(Protocol):
    def save(self, asset: GeneratedAsset) -> None:
        ...

    def get(self, owner_user_id: str, asset_id: str) -> Optional[GeneratedAsset]:
        ...

    def find_by_job(self, owner_user_id: str, job_id: str) -> Optional[GeneratedAsset]:
        ...
