import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hermes_personal.product_video.handlers import (
    JobContext,
    JobFailed,
    JobSucceeded,
    MCPVideoFactoryAdapter,
    ProductVideoJobHandlers,
    TerminalJobError,
)
from hermes_personal.product_video.mcp_adapters import _dispatch_tool
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.budgets import BudgetPolicy, get_reservation, init_default_engine
from hermes_personal.workflows.repository import WorkflowRepository


@pytest.fixture
def durable(tmp_path):
    conn = connect(tmp_path / 'workflow.db')
    engine = init_default_engine(BudgetPolicy(1000, {'video_factory': 1000}), connection=conn)
    yield WorkflowRepository(conn), engine
    conn.close()


def save(repo, **fields):
    repo.commit_workflow('wf', json.dumps({'owner_user_id': 'owner', 'project_id': 'proj_wf', **fields}), [], expected_version=0)


def test_export_executes_after_validating_workflow(durable):
    repo, _ = durable
    save(repo, state='exporting')
    result = ProductVideoJobHandlers(workflow_repository=repo).export_job(
        JobContext('wf', 'export', owner_user_id='owner', idempotency_key='export'), 'render')
    assert isinstance(result, JobSucceeded)


def test_completed_render_replay_settles_reservation(durable):
    repo, engine = durable
    alloc = engine.reserve_budget('video_factory', 50, owner_user_id='owner')
    save(repo, state='rendering', render_dispatch_status='COMPLETED', render_result={'render_id': 'r'},
         render_budget_reservation_id=alloc.reservation_id)
    result = ProductVideoJobHandlers(workflow_repository=repo).render_job(
        JobContext('wf', 'render', owner_user_id='owner'), 'story')
    assert isinstance(result, JobSucceeded)
    assert get_reservation(alloc.reservation_id).state == 'committed'


def test_completed_render_missing_reservation_fails_closed(durable):
    repo, _ = durable
    save(repo, state='rendering', render_dispatch_status='COMPLETED', render_result={'render_id': 'r'},
         render_budget_reservation_id='absent')
    result = ProductVideoJobHandlers(workflow_repository=repo).render_job(
        JobContext('wf', 'render', owner_user_id='owner'), 'story')
    assert isinstance(result, JobFailed)
    assert result.code == 'BUDGET_RECOVERY_FAILED'


def test_mcp_reconciliation_status_keeps_terminal_code():
    registry = {'poll': lambda _payload: {
        'ok': False,
        'status': 'reconciliation_required',
        'code': 'RECONCILIATION_REQUIRED',
        'error': 'Flow tile is not visible yet',
    }}
    with pytest.raises(TerminalJobError) as exc:
        _dispatch_tool(registry, 'poll', {'job_id': 'flow-job'})
    assert exc.value.code == 'RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('error_code', ['RECONCILIATION_REQUIRED', 'VF_CHECKPOINT_FAILED'])
def test_ambiguous_render_keeps_budget_reservation(durable, monkeypatch, error_code):
    repo, _ = durable
    save(repo, state='rendering')
    provider = MagicMock()
    provider.require_execution_binding.return_value = 'mcp__video_factory__render'
    provider.render_video.side_effect = TerminalJobError(
        'Flow acceptance could not be confirmed', code=error_code
    )
    allocation = SimpleNamespace(reservation_id='reserved-flow-call')
    monkeypatch.setattr('hermes_personal.product_video.handlers.reserve_budget', lambda *_args, **_kwargs: allocation)
    released = []
    monkeypatch.setattr('hermes_personal.product_video.handlers.release_budget', released.append)

    result = ProductVideoJobHandlers(
        workflow_repository=repo,
        video_client=provider,
        provider_mode='configured',
    ).render_job(
        JobContext('wf', 'render', owner_user_id='owner'),
        'story',
        qc_authorization={'max_cost_usd': 1.00},
    )

    assert isinstance(result, JobFailed)
    assert result.code == error_code
    assert result.retryable is False
    assert released == []


def test_render_timeout_before_acceptance_stops_paid_retry(durable, monkeypatch):
    repo, _ = durable
    save(repo, state='rendering')
    provider = MagicMock()
    provider.require_execution_binding.return_value = 'mcp__video_factory__render'
    provider.render_video.side_effect = TimeoutError('provider response lost')
    allocation = SimpleNamespace(reservation_id='reserved-flow-call')
    monkeypatch.setattr('hermes_personal.product_video.handlers.reserve_budget', lambda *_args, **_kwargs: allocation)
    released = []
    monkeypatch.setattr('hermes_personal.product_video.handlers.release_budget', released.append)

    result = ProductVideoJobHandlers(
        workflow_repository=repo, video_client=provider, provider_mode='configured'
    ).render_job(
        JobContext('wf', 'render', owner_user_id='owner'),
        'story', qc_authorization={'max_cost_usd': 1.00},
    )

    assert isinstance(result, JobFailed)
    assert result.code == 'UNKNOWN_PAID_OUTCOME'
    assert result.retryable is False
    assert released == []


def test_accepted_render_retry_reuses_and_commits_budget(durable):
    repo, _ = durable
    save(repo, state='rendering')

    class Provider:
        calls = 0

        def require_execution_binding(self, *_args):
            return 'mcp__video_factory__render'

        def render_video(self, _story, *, render_params, on_job_accepted, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                on_job_accepted('render', 'accepted-job')
                raise TimeoutError('poll timed out')
            assert render_params['active_job_id'] == 'accepted-job'
            return {'render_id': 'finished-render'}

    provider = Provider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo, video_client=provider, provider_mode='configured'
    )
    ctx = JobContext('wf', 'render', owner_user_id='owner', idempotency_key='same-render')
    first = handlers.render_job(ctx, 'story', qc_authorization={'max_cost_usd': 1.00})
    aggregate, _ = repo.get_workflow('wf')
    reservation_id = aggregate['render_budget_reservation_id']
    second = handlers.render_job(ctx, 'story')

    assert isinstance(first, JobFailed) and first.retryable is True
    assert aggregate['active_render_job_id'] == 'accepted-job'
    assert get_reservation(reservation_id).state == 'committed'
    assert isinstance(second, JobSucceeded)
    assert provider.calls == 2


def test_render_rejects_unbound_resume_job(durable):
    repo, _ = durable
    save(repo, state='rendering')
    result = ProductVideoJobHandlers(workflow_repository=repo).render_job(
        JobContext('wf', 'render', owner_user_id='owner'), 'story', {'active_job_id': 'foreign'})
    assert isinstance(result, JobFailed)
    assert result.code == 'JOB_BINDING_MISMATCH'


def test_configured_render_requires_unexpired_scoped_cost_authorization(durable):
    repo, _ = durable
    save(repo, state='rendering')
    provider = MagicMock()
    provider.require_execution_binding.return_value = 'mcp__video_factory__render'
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode='configured',
    )

    result = handlers.render_job(JobContext('wf', 'render', owner_user_id='owner'), 'story')

    assert isinstance(result, JobFailed)
    assert result.code == 'COST_AUTHORIZATION_REQUIRED'
    provider.render_video.assert_not_called()


def test_configured_render_rejects_authorization_below_durable_admission(durable):
    repo, _ = durable
    save(repo, state='rendering')
    provider = MagicMock()
    provider.require_execution_binding.return_value = 'mcp__video_factory__render'
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode='configured',
    )
    authorization = {
        'workflow_id': 'wf',
        'run_id': 'cost-run-001',
        'scope': ['product_video'],
        'expires_at': '2099-01-01T00:00:00+00:00',
        'max_cost_usd': 0.49,
    }

    result = handlers.render_job(
        JobContext('wf', 'render', owner_user_id='owner'),
        'story',
        qc_authorization=authorization,
    )

    assert isinstance(result, JobFailed)
    assert result.code == 'COST_AUTHORIZATION_REQUIRED'
    provider.render_video.assert_not_called()


@pytest.mark.parametrize(
    ("state", "stage", "input_ref"),
    [
        ("rendering", "render", "story"),
        ("exporting", "export", "render"),
    ],
)
def test_configured_execution_without_binding_preflight_fails_before_budget_or_dispatch(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
):
    class VideoClientWithoutExecutionBinding:
        def __init__(self):
            self.dispatches: list[str] = []

        def render_video(self, *_args, **_kwargs):
            self.dispatches.append("render")
            raise AssertionError("render dispatch must not be reached")

        def export_video(self, *_args, **_kwargs):
            self.dispatches.append("export")
            raise AssertionError("export dispatch must not be reached")

    repo, _ = durable
    save(repo, state=state)
    provider = VideoClientWithoutExecutionBinding()
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: (
            reservations.append((channel, amount))
            or SimpleNamespace(reservation_id="unexpected-reservation")
        ),
    )
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    job = getattr(handlers, f"{stage}_job")
    result = job(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.code == "BINDING_UNAVAILABLE"
    assert stage in result.message
    assert provider.dispatches == []
    assert reservations == []


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "capability_id", "wire"),
    [
        ("rendering", "render", "story", "video.render", "mcp__video_factory__render"),
        ("exporting", "export", "render", "video.export", "mcp__custom_video_factory__export"),
    ],
)
def test_configured_execution_uses_duck_typed_binding_preflight(
    durable,
    state,
    stage,
    input_ref,
    capability_id,
    wire,
):
    class VideoClientWithExecutionBinding:
        def __init__(self):
            self.preflights: list[tuple[str, str]] = []
            self.dispatches: list[str] = []

        def require_execution_binding(self, stage_key, requested_capability_id):
            self.preflights.append((stage_key, requested_capability_id))
            return wire

        def render_video(self, *_args, **_kwargs):
            self.dispatches.append("render")
            return {"render_id": "duck-typed-render"}

        def export_video(self, *_args, **_kwargs):
            self.dispatches.append("export")
            return {"export_id": "duck-typed-export"}

    repo, _ = durable
    save(repo, state=state)
    provider = VideoClientWithExecutionBinding()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobSucceeded)
    assert provider.preflights == [(stage, capability_id)]
    assert provider.dispatches == [stage]


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "durable_job_id", "requested_job_id"),
    [
        ("rendering", "render", "story", "active_render_job_id", "durable-render", "other-render"),
        ("rendering", "render", "story", "active_render_job_id", None, "unbound-render"),
        ("exporting", "export", "render", "active_export_job_id", "durable-export", "other-export"),
        ("exporting", "export", "render", "active_export_job_id", None, "unbound-export"),
    ],
)
def test_resume_rejects_any_requested_job_id_not_matching_durable_identity(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    durable_job_id,
    requested_job_id,
):
    class Provider:
        def __init__(self):
            self.preflights: list[tuple[str, str]] = []
            self.dispatches: list[str] = []

        def require_execution_binding(self, stage_key, capability_id):
            self.preflights.append((stage_key, capability_id))
            return "mcp__video_factory__render"

        def render_video(self, *_args, **_kwargs):
            self.dispatches.append("render")
            raise AssertionError("mismatched resume must not dispatch")

        def export_video(self, *_args, **_kwargs):
            self.dispatches.append("export")
            raise AssertionError("mismatched resume must not dispatch")

    repo, _ = durable
    fields = {"state": state}
    if durable_job_id is not None:
        fields[durable_key] = durable_job_id
    save(repo, **fields)
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = Provider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        {"active_job_id": requested_job_id},
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.code == "JOB_BINDING_MISMATCH"
    assert requested_job_id in result.message
    assert provider.preflights == []
    assert provider.dispatches == []
    assert reservations == []


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "durable_job_id", "requested_job_id"),
    [
        ("rendering", "render", "story", "active_render_job_id", "durable-render", "  durable-render  "),
        ("rendering", "render", "story", "active_render_job_id", "durable-render", None),
        ("exporting", "export", "render", "active_export_job_id", "durable-export", "  durable-export  "),
        ("exporting", "export", "render", "active_export_job_id", "durable-export", None),
    ],
)
def test_resume_uses_normalized_durable_job_identity_without_preflight_or_reservation(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    durable_job_id,
    requested_job_id,
):
    class ResumeProvider:
        def __init__(self):
            self.preflight_called = False
            self.params: dict | None = None

        def require_execution_binding(self, *_args):
            self.preflight_called = True
            raise AssertionError("resume must not preflight submit binding")

        def render_video(self, _story_ref, *, render_params, **_kwargs):
            self.params = render_params
            return {"render_id": "resumed-render"}

        def export_video(self, _render_ref, *, export_params, **_kwargs):
            self.params = export_params
            return {"export_id": "resumed-export"}

    repo, _ = durable
    save(repo, state=state, **{durable_key: f"  {durable_job_id}  "})
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = ResumeProvider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    params = {"active_job_id": requested_job_id} if requested_job_id is not None else {}
    result = getattr(handlers, f"{stage}_job")(JobContext("wf", stage, owner_user_id="owner"), input_ref, params)

    assert isinstance(result, JobSucceeded)
    assert provider.preflight_called is False
    assert provider.params == {"active_job_id": durable_job_id}
    assert reservations == []


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "durable_job_id", "params"),
    [
        ("rendering", "render", "story", "active_render_job_id", None, {"job_id": "render-unbound"}),
        ("rendering", "render", "story", "active_render_job_id", "render-durable", {"job_id": "render-durable"}),
        ("rendering", "render", "story", "active_render_job_id", "render-durable", {"job_id": "render-other"}),
        ("rendering", "render", "story", "active_render_job_id", "render-durable", {"active_job_id": "render-durable", "job_id": "render-durable"}),
        ("rendering", "render", "story", "active_render_job_id", "render-durable", {"active_job_id": "render-durable", "job_id": "render-other"}),
        ("exporting", "export", "render", "active_export_job_id", None, {"job_id": "export-unbound"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"job_id": "export-durable"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"job_id": "export-other"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"export_id": "export-durable"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"export_id": "export-other"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"active_job_id": "export-durable", "job_id": "export-durable", "export_id": "export-durable"}),
        ("exporting", "export", "render", "active_export_job_id", "export-durable", {"active_job_id": "export-durable", "job_id": "export-other", "export_id": "export-durable"}),
    ],
)
def test_resume_identity_aliases_fail_closed_before_handler_side_effects(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    durable_job_id,
    params,
):
    class Provider:
        def __init__(self):
            self.preflights = 0
            self.dispatches = 0

        def require_execution_binding(self, *_args):
            self.preflights += 1
            raise AssertionError("aliases must fail before preflight")

        def render_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("aliases must fail before render dispatch")

        def export_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("aliases must fail before export dispatch")

    repo, _ = durable
    fields = {"state": state}
    if durable_job_id is not None:
        fields[durable_key] = durable_job_id
    save(repo, **fields)
    before = repo.get_workflow("wf")
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = Provider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        dict(params),
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.retryable is False
    assert result.code == "JOB_BINDING_MISMATCH"
    assert "noncanonical_resume_identity" in result.message
    assert provider.preflights == 0
    assert provider.dispatches == 0
    assert reservations == []
    assert repo.get_workflow("wf") == before


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "params"),
    [
        ("rendering", "render", "story", {"job_id": " \t"}),
        ("exporting", "export", "render", {"job_id": " ", "export_id": "\n"}),
    ],
)
def test_empty_resume_aliases_are_removed_before_fresh_adapter_dispatch(
    durable,
    state,
    stage,
    input_ref,
    params,
):
    class Provider:
        def __init__(self):
            self.preflights = 0
            self.params: dict | None = None

        def require_execution_binding(self, *_args):
            self.preflights += 1
            return "mcp__video_factory__render" if stage == "render" else "mcp__custom__export"

        def render_video(self, _story_ref, *, render_params, **_kwargs):
            self.params = render_params
            return {"render_id": "fresh-render"}

        def export_video(self, _render_ref, *, export_params, **_kwargs):
            self.params = export_params
            return {"export_id": "fresh-export"}

    repo, _ = durable
    save(repo, state=state)
    provider = Provider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        dict(params),
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobSucceeded)
    assert provider.preflights == 1
    assert provider.params is not None
    assert "job_id" not in provider.params
    assert "export_id" not in provider.params


def test_direct_mcp_adapter_keeps_manual_job_id_resume_compatibility():
    class Registry:
        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def get_all_tool_names(self):
            return {"mcp__video_factory__get_job_status"}

        def dispatch(self, name, payload):
            self.calls.append((name, payload))
            return {
                "status": "completed",
                "job_id": "manual-job",
                "video_url": "https://example.invalid/manual-resume.mp4",
                "owner_user_id": "owner",
                "project_id": "project",
                "workflow_id": "workflow",
                "artifact_id": "artifact",
                "artifact_version": 1,
                "sha256": "sha256:" + "a" * 64,
            }

    registry = Registry()
    adapter = MCPVideoFactoryAdapter(
        registry,
        {"get_job_status": "mcp__video_factory__get_job_status"},
        poll_interval=0.001,
    )

    result = adapter.render_video({}, render_params={"job_id": "manual-job"})

    assert result["external_provider_id"] == "manual-job"
    assert registry.calls == [("mcp__video_factory__get_job_status", {"job_id": "manual-job"})]


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "invalid_params"),
    [
        ("rendering", "render", "story", "active_render_job_id", {"job_id": "alias-render"}),
        ("rendering", "render", "story", "active_render_job_id", {"active_job_id": "wrong-render"}),
        ("exporting", "export", "render", "active_export_job_id", {"export_id": "alias-export"}),
        ("exporting", "export", "render", "active_export_job_id", {"active_job_id": "wrong-export"}),
    ],
)
def test_invalid_resume_identity_precedes_idempotency_cache_hit(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    invalid_params,
):
    class Provider:
        def require_execution_binding(self, *_args):
            raise AssertionError("invalid identity must precede preflight")

        def render_video(self, *_args, **_kwargs):
            raise AssertionError("invalid identity must precede provider dispatch")

        def export_video(self, *_args, **_kwargs):
            raise AssertionError("invalid identity must precede provider dispatch")

    repo, _ = durable
    durable_job_id = f"durable-{stage}"
    save(repo, state=state, **{durable_key: durable_job_id})
    before = repo.get_workflow("wf")
    _aggregate, version = before
    ctx = JobContext("wf", stage, owner_user_id="owner", idempotency_key="cached-attempt")
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=Provider(),
        provider_mode="configured",
    )
    handlers._idempotency_cache[f"wf:{stage}:v{version}:cached-attempt"] = JobSucceeded(
        artifact_ref={"cached": stage}
    )
    budget_calls: list[str] = []
    monkeypatch.setattr("hermes_personal.product_video.handlers.reserve_budget", lambda *_args, **_kwargs: budget_calls.append("reserve"))
    monkeypatch.setattr("hermes_personal.product_video.handlers.commit_budget", lambda *_args, **_kwargs: budget_calls.append("commit"))
    monkeypatch.setattr("hermes_personal.product_video.handlers.release_budget", lambda *_args, **_kwargs: budget_calls.append("release"))

    result = getattr(handlers, f"{stage}_job")(ctx, input_ref, invalid_params)

    assert isinstance(result, JobFailed)
    assert result.code == "JOB_BINDING_MISMATCH"
    assert result.retryable is False
    assert budget_calls == []
    assert repo.get_workflow("wf") == before


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "status_key", "reservation_key", "result_key", "invalid_params"),
    [
        ("rendering", "render", "story", "active_render_job_id", "render_dispatch_status", "render_budget_reservation_id", "render_result", {"export_id": "alias-render"}),
        ("rendering", "render", "story", "active_render_job_id", "render_dispatch_status", "render_budget_reservation_id", "render_result", {"active_job_id": "wrong-render"}),
        ("exporting", "export", "render", "active_export_job_id", "export_dispatch_status", "export_budget_reservation_id", "export_result", {"job_id": "alias-export"}),
        ("exporting", "export", "render", "active_export_job_id", "export_dispatch_status", "export_budget_reservation_id", "export_result", {"active_job_id": "wrong-export"}),
    ],
)
def test_invalid_resume_identity_precedes_completed_recovery_side_effects(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    status_key,
    reservation_key,
    result_key,
    invalid_params,
):
    class Provider:
        def require_execution_binding(self, *_args):
            raise AssertionError("invalid identity must precede preflight")

        def render_video(self, *_args, **_kwargs):
            raise AssertionError("invalid identity must precede provider dispatch")

        def export_video(self, *_args, **_kwargs):
            raise AssertionError("invalid identity must precede provider dispatch")

    repo, _ = durable
    save(
        repo,
        state=state,
        **{
            durable_key: f"durable-{stage}",
            status_key: "COMPLETED",
            reservation_key: "res-should-not-load",
            result_key: {"completed": stage},
        },
    )
    before = repo.get_workflow("wf")
    recovery_calls: list[str] = []
    monkeypatch.setattr("hermes_personal.product_video.handlers.get_reservation", lambda *_args, **_kwargs: recovery_calls.append("get"))
    monkeypatch.setattr("hermes_personal.product_video.handlers.commit_budget", lambda *_args, **_kwargs: recovery_calls.append("commit"))
    provider = Provider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(JobContext("wf", stage, owner_user_id="owner"), input_ref, invalid_params)

    assert isinstance(result, JobFailed)
    assert result.code == "JOB_BINDING_MISMATCH"
    assert result.retryable is False
    assert recovery_calls == []
    assert repo.get_workflow("wf") == before


@pytest.mark.parametrize(
    ("state", "stage", "input_ref", "durable_key", "status_key", "reservation_key", "result_key"),
    [
        ("rendering", "render", "story", "active_render_job_id", "render_dispatch_status", "render_budget_reservation_id", "render_result"),
        ("exporting", "export", "render", "active_export_job_id", "export_dispatch_status", "export_budget_reservation_id", "export_result"),
    ],
)
def test_valid_completed_recovery_runs_after_auto_resolving_durable_identity(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
    durable_key,
    status_key,
    reservation_key,
    result_key,
):
    class Provider:
        def require_execution_binding(self, *_args):
            raise AssertionError("completed recovery must not preflight")

        def render_video(self, *_args, **_kwargs):
            raise AssertionError("completed recovery must not dispatch")

        def export_video(self, *_args, **_kwargs):
            raise AssertionError("completed recovery must not dispatch")

    repo, engine = durable
    reservation = engine.reserve_budget("video_factory", 50 if stage == "render" else 20, owner_user_id="owner")
    expected_result = {"completed": stage}
    save(
        repo,
        state=state,
        **{
            durable_key: f"durable-{stage}",
            status_key: "COMPLETED",
            reservation_key: reservation.reservation_id,
            result_key: expected_result,
        },
    )
    recovery_calls: list[str] = []
    original_get = __import__("hermes_personal.product_video.handlers", fromlist=["get_reservation"]).get_reservation
    original_commit = __import__("hermes_personal.product_video.handlers", fromlist=["commit_budget"]).commit_budget
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.get_reservation",
        lambda reservation_id: (recovery_calls.append("get") or original_get(reservation_id)),
    )
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.commit_budget",
        lambda allocation: (recovery_calls.append("commit") or original_commit(allocation)),
    )
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=Provider(),
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(JobContext("wf", stage, owner_user_id="owner"), input_ref)

    assert isinstance(result, JobSucceeded)
    assert result.artifact_ref == expected_result
    assert recovery_calls == ["get", "commit"]


@pytest.mark.parametrize(
    "wire",
    [
        "video_generate",
        "mcp__vertex_ai__render",
        "mcp__video_factory__export",
        "mcp__video_factory__render_alias",
        " mcp__video_factory__render ",
    ],
)
def test_configured_render_rejects_duck_typed_noncanonical_preflight_wire_before_budget_or_dispatch(
    durable,
    monkeypatch,
    wire,
):
    class AliasPreflightProvider:
        def __init__(self):
            self.dispatches = 0

        def require_execution_binding(self, *_args):
            return wire

        def render_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("noncanonical render wire must not dispatch")

    repo, _ = durable
    save(repo, state="rendering")
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = AliasPreflightProvider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = handlers.render_job(
        JobContext("wf", "render", owner_user_id="owner"),
        "story",
        qc_authorization={"max_cost_usd": 1.00},
    )

    assert isinstance(result, JobFailed)
    assert result.code == "BINDING_UNAVAILABLE"
    assert "noncanonical_wire" in result.message
    assert provider.dispatches == 0
    assert reservations == []


@pytest.mark.parametrize(
    ("state", "stage", "input_ref"),
    [
        ("rendering", "render", "story"),
        ("exporting", "export", "render"),
    ],
)
def test_unexpected_execution_binding_preflight_failure_is_not_binding_unavailable(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
):
    class ExplodingPreflightProvider:
        def __init__(self):
            self.dispatches = 0

        def require_execution_binding(self, *_args):
            raise RuntimeError("programming fault")

        def render_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("preflight failure must not dispatch")

        def export_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("preflight failure must not dispatch")

    repo, _ = durable
    save(repo, state=state)
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = ExplodingPreflightProvider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.retryable is False
    assert result.code == "BINDING_PREFLIGHT_FAILED"
    assert provider.dispatches == 0
    assert reservations == []


@pytest.mark.parametrize(
    ("state", "stage", "input_ref"),
    [
        ("rendering", "render", "story"),
        ("exporting", "export", "render"),
    ],
)
def test_terminal_preflight_binding_rejection_preserves_adapter_code(
    durable,
    monkeypatch,
    state,
    stage,
    input_ref,
):
    class TerminalBindingProvider:
        def __init__(self):
            self.dispatches = 0

        def require_execution_binding(self, *_args):
            raise TerminalJobError("snapshot binding is unavailable", code="BINDING_UNAVAILABLE")

        def render_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("terminal preflight rejection must not dispatch")

        def export_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("terminal preflight rejection must not dispatch")

    repo, _ = durable
    save(repo, state=state)
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = TerminalBindingProvider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.code == "BINDING_UNAVAILABLE"
    assert provider.dispatches == 0
    assert reservations == []


@pytest.mark.parametrize("invalid_wire", [None, "", 123])
@pytest.mark.parametrize(
    ("state", "stage", "input_ref"),
    [
        ("rendering", "render", "story"),
        ("exporting", "export", "render"),
    ],
)
def test_invalid_preflight_result_fails_closed_before_budget_or_dispatch(
    durable,
    monkeypatch,
    invalid_wire,
    state,
    stage,
    input_ref,
):
    class InvalidPreflightProvider:
        def __init__(self):
            self.dispatches = 0

        def require_execution_binding(self, *_args):
            return invalid_wire

        def render_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("invalid preflight result must not dispatch")

        def export_video(self, *_args, **_kwargs):
            self.dispatches += 1
            raise AssertionError("invalid preflight result must not dispatch")

    repo, _ = durable
    save(repo, state=state)
    reservations: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.reserve_budget",
        lambda channel, amount, **_kwargs: reservations.append((channel, amount)),
    )
    provider = InvalidPreflightProvider()
    handlers = ProductVideoJobHandlers(
        workflow_repository=repo,
        pi_client=MagicMock(),
        video_client=provider,
        provider_mode="configured",
    )

    result = getattr(handlers, f"{stage}_job")(
        JobContext("wf", stage, owner_user_id="owner"),
        input_ref,
        qc_authorization={"max_cost_usd": 1.00} if stage == "render" else None,
    )

    assert isinstance(result, JobFailed)
    assert result.code == "BINDING_UNAVAILABLE"
    assert "invalid_preflight_result" in result.message
    assert provider.dispatches == 0
    assert reservations == []


def test_export_rejects_unbound_resume_job(durable):
    repo, _ = durable
    save(repo, state='exporting')
    result = ProductVideoJobHandlers(workflow_repository=repo).export_job(
        JobContext('wf', 'export', owner_user_id='owner'), 'render', {'active_job_id': 'foreign'})
    assert isinstance(result, JobFailed)
    assert result.code == 'JOB_BINDING_MISMATCH'


@pytest.mark.parametrize('status', ['DISPATCHING', 'UNKNOWN_OUTCOME'])
def test_export_unknown_never_resubmits(durable, status):
    repo, _ = durable
    save(repo, state='exporting', export_dispatch_status=status)
    result = ProductVideoJobHandlers(workflow_repository=repo).export_job(
        JobContext('wf', 'export', owner_user_id='owner'), 'render')
    assert isinstance(result, JobFailed)
    assert result.code == 'UNKNOWN_PAID_OUTCOME'


def test_export_completed_replay_returns_durable_result(durable):
    repo, engine = durable
    allocation = engine.reserve_budget('video_factory', 20, owner_user_id='owner',
                                       scope_id='wf', capability_id='video.export')
    save(repo, state='exporting', export_dispatch_status='COMPLETED',
         export_result={'export_id': 'durable'}, export_budget_reservation_id=allocation.reservation_id)
    result = ProductVideoJobHandlers(workflow_repository=repo).export_job(
        JobContext('wf', 'export', owner_user_id='owner'), 'render')
    assert isinstance(result, JobSucceeded)
    assert result.artifact_ref == {'export_id': 'durable'}
    assert get_reservation(allocation.reservation_id).state == 'committed'
