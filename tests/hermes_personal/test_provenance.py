from hermes_personal.provenance import load_upstream_baseline


def test_pinned_upstream_baseline_is_traceable_and_unrelated():
    baseline = load_upstream_baseline()

    assert baseline.schema_version == 1
    assert baseline.upstream_repository == "https://github.com/NousResearch/hermes-agent.git"
    assert baseline.upstream_branch == "main"
    assert baseline.upstream_sha == "0012dd1e0c7efc7e86fa75b89567a492057f0c02"
    assert baseline.legacy_repository == "https://github.com/khoahuynhanh97/hermes-agent.git"
    assert baseline.legacy_branch == "codex/hermes-orchestrator-unification"
    assert baseline.legacy_head == "9d63f406f264b3513af9e369bb8d8638f4c02261"
    assert baseline.history_relation == "unrelated"
