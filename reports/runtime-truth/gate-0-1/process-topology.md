# Process Topology Audit: Declared vs Tested vs Observed

This document audits all processes configured and built by `hermes_personal.runtime.processes.build_process_topology()`, rigorously separating configuration layers and distinguishing test execution from observed OS processes.

---

## 1. Configuration Layer Distinction

Three distinct configuration layers govern the process topology:

1. **`RuntimeConfig` Dataclass Source Defaults** (`hermes_personal/runtime/config.py:25`):
   - `enable_telegram`: `True`
   - `enable_web`: `True`
   - `enable_workers`: `True`
   - `enable_mcp`: `True`
   - `provider_mode`: `"configured"`
   *(Note: Invoking `hermes start` with no arguments uses these defaults, which enables all 6 processes including the missing runner targets).*

2. **Local Example Configuration** (`runtime-config.local.yaml.example`):
   - `enable_web`: `true`
   - `enable_telegram`: `false`
   - `enable_workers`: `false`
   - `enable_mcp`: `false`
   - `provider_mode`: `fake`
   *(Note: The local example declares the intended reduced topology; real-process success remains unobserved in Gate 1).*

3. **Explicit Operator Configuration**:
   - Supplied via `--config <path>` at runtime, overriding individual flags as needed.

---

## 2. Process Topology Inventory

| Process Name | `runtime_status` | Config Gate | Target Module / Command | Target on Disk? | Readiness Probe | Evidence Level & Test Proof |
| :--- | :---: | :---: | :--- | :---: | :--- | :--- |
| **`gateway`** | **TESTED** | Required (Always ON) | `python -m hermes_personal.runtime.gateway_server --port {gateway_port} --provider-mode {provider_mode}` | **YES** (`hermes_personal/runtime/gateway_server.py`) | `HTTP GET http://127.0.0.1:{gateway_port}/health/ready` | **TESTED**. Exercised in `tests/hermes_personal/runtime/test_gateway_server.py`, `tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py`, and `tests/hermes_personal/e2e/test_runtime_smoke.py` via ASGI TestClient and SmokeRunner. Not OBSERVED as a standalone background OS daemon. |
| **`app_api`** | **TESTED** | Required (Always ON) | `python -m hermes_personal.api.server --port {app_api_port} --gateway-port {gateway_port}` | **YES** (`hermes_personal/api/server.py`) | `HTTP GET http://127.0.0.1:{app_api_port}/healthz` | **TESTED**. Exercised in `tests/hermes_personal/runtime/test_application_api.py`. |
| **`mcp_discovery`** | **DECLARED** (MISSING_TARGET) | `enable_mcp: true` (Dataclass default: True; Example: False) | `python -m hermes_personal.capabilities.mcp_runner --action discover` | **NO** (`hermes_personal/capabilities/mcp_runner.py` MISSING_TARGET) | `EXEC mcp_snapshot_check` | **DECLARED ONLY**. Target module does not exist on disk. Documented as known gap HP-002. |
| **`durable_worker`** | **TESTED** | `enable_workers: true` (Dataclass default: True; Example: False) | `python -m hermes_personal.workflows.worker` | **YES** (`hermes_personal/workflows/worker.py`) | `NOOP` | **TESTED**. Exercised in `tests/hermes_personal/workflows/test_worker.py` and `tests/hermes_personal/workflows/test_product_video_outbox.py`. |
| **`telegram`** | **DECLARED** (MISSING_TARGET) | `enable_telegram: true` (Dataclass default: True; Example: False) | `python -m hermes_personal.gateway.platforms.telegram_runner` | **NO** (`hermes_personal/gateway/platforms/telegram_runner.py` MISSING_TARGET) | `NOOP` | **DECLARED ONLY**. Target module does not exist on disk. Documented as known gap HP-002. Upstream Telegram gateway runs via `gateway/run.py`. |
| **`web_ui`** | **TESTED** | `enable_web: true` & `mode: development` | `node run dev -- --host 127.0.0.1 --port {web_port}` | **YES** (`web/` directory) | `HTTP GET http://127.0.0.1:{web_port}` | **TESTED**. Argv and command resolution tested in `tests/hermes_personal/runtime/test_processes.py`. |
