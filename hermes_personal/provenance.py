from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal


@dataclass(frozen=True)
class UpstreamBaseline:
    schema_version: int
    upstream_repository: str
    upstream_branch: str
    upstream_sha: str
    observed_at: str
    legacy_repository: str
    legacy_branch: str
    legacy_head: str
    history_relation: Literal["unrelated"]


def load_upstream_baseline() -> UpstreamBaseline:
    resource = files("hermes_personal").joinpath("data", "upstream-baseline.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    baseline = UpstreamBaseline(**payload)
    if baseline.schema_version != 1:
        raise ValueError(f"Unsupported upstream baseline schema: {baseline.schema_version}")
    if baseline.history_relation != "unrelated":
        raise ValueError(f"Unsupported history relation: {baseline.history_relation}")
    for field_name in ("upstream_sha", "legacy_head"):
        value = getattr(baseline, field_name)
        if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"Invalid {field_name}: {value!r}")
    return baseline
