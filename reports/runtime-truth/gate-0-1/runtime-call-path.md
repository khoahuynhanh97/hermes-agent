# Runtime Call Path Trace: `hermes start`

This document traces the exact execution chain of `hermes start` from the public Hermes CLI entrypoint through plugin discovery, configuration, startup coordination, and supervisor execution. Every symbol and line number is resolved directly from current HEAD.

---

## 1. Detailed Call Chain & Symbol Trace

```
pyproject.toml:373 [project.scripts]
  └── hermes = "hermes_cli.main:main"
        ↓
hermes_cli/main.py:12418 (main)
  ├── hermes_cli/_parser.py:87 (build_top_level_parser)
  └── hermes_cli/main.py:11735 (_plugin_cli_discovery_needed)
        ↓
hermes_cli/plugins.py:5699 (discover_plugins)
  └── scans plugins/ for plugin.yaml manifests
  └── discovers plugins/hermes_personal/plugin.yaml (name: hermes-personal, kind: standalone)
        ↓
hermes_cli/plugins.py:4758 (PluginManager._load_plugin)
  └── imports plugins/hermes_personal/__init__.py
  └── calls plugins/hermes_personal/__init__.py:7 (register)
        ↓
plugins/hermes_personal/__init__.py:7 (register)
  └── calls hermes_personal/runtime/plugin.py:11 (register)
        ↓
hermes_personal/runtime/plugin.py:11 (register)
  └── calls ctx.register_cli_command(
            name="start",
            help="Start the complete Hermes personal runtime",
            description="Validate, recover, start, and supervise every Hermes service.",
            setup_fn=setup_start_parser,
            handler_fn=handle_start,
        )
        ↓
hermes_cli/plugins.py:2066 (PluginContext.register_cli_command)
  └── stores command info in PluginManager._cli_commands["start"]
        ↓
hermes_cli/main.py (lines 12981-12992)
  └── wires subparser for "start":
        plugin_parser = subparsers.add_parser("start", ...)
        setup_start_parser(plugin_parser)
        plugin_parser.set_defaults(func=handle_start)
        ↓
[User Invocation: hermes start [--mode MODE] [--config CONFIG] [--no-open-browser]]
        ↓
hermes_personal/runtime/cli.py:23 (setup_start_parser)
  └── adds --mode, --config, --no-open-browser CLI arguments
        ↓
hermes_personal/runtime/cli.py:44 (handle_start)
  ├── 1. Configuration Construction:
  │      if args.config:
  │          config = RuntimeConfig.from_file(config_path=args.config, mode=mode, repo_root=repo_root) (config.py:85)
  │      else:
  │          config = RuntimeConfig(mode=mode or "development", repo_root=repo_root)
  │
  ├── 2. Startup Coordinator:
  │      coordinator = StartupCoordinator(config=config, env=dict(os.environ))
  │      report = coordinator.prepare() (startup.py:221)
  │
  ├── 3. Topology Construction:
  │      specs = build_process_topology(config) (processes.py:69)
  │
  ├── 4. Environment Seeding:
  │      os.environ["HERMES_PORT"] = str(config.gateway_port)
  │      os.environ["HERMES_API_PORT"] = str(config.app_api_port)
  │      os.environ["HERMES_DASHBOARD_URL"] = f"http://127.0.0.1:{config.app_api_port}"
  │      os.environ["PORT"] = str(config.web_port)
  │
  └── 5. Supervisor Execution:
         supervisor = Supervisor(specs=specs, runner=DefaultProcessRunner()) (supervisor.py:169)
         exit_code = supervisor.run() (supervisor.py:477)
           └── DefaultProcessRunner.start(spec) spawns subprocesses (supervisor.py:124)
           └── Supervisor._wait_for_readiness(spec, child) probes ProbeSpec
```

---

## 2. Recomputed Symbol Line Numbers Table

| Symbol | File Path | Line | Status |
| :--- | :--- | :---: | :---: |
| `hermes_cli.main:main` | `hermes_cli/main.py` | `12418` | VERIFIED |
| `hermes_cli._parser:build_top_level_parser` | `hermes_cli/_parser.py` | `87` | VERIFIED |
| `hermes_cli.main:_plugin_cli_discovery_needed` | `hermes_cli/main.py` | `11735` | VERIFIED |
| `hermes_cli.plugins:discover_plugins` | `hermes_cli/plugins.py` | `5699` | VERIFIED |
| `PluginManager._load_plugin` | `hermes_cli/plugins.py` | `4758` | VERIFIED |
| `PluginContext.register_cli_command` | `hermes_cli/plugins.py` | `2066` | VERIFIED |
| `plugins.hermes_personal:register` | `plugins/hermes_personal/__init__.py` | `7` | VERIFIED |
| `hermes_personal.runtime.plugin:register` | `hermes_personal/runtime/plugin.py` | `11` | VERIFIED |
| `setup_start_parser` | `hermes_personal/runtime/cli.py` | `23` | VERIFIED |
| `handle_start` | `hermes_personal/runtime/cli.py` | `44` | VERIFIED |
| `RuntimeConfig.from_file` | `hermes_personal/runtime/config.py` | `85` | VERIFIED |
| `StartupCoordinator.prepare` | `hermes_personal/runtime/startup.py` | `221` | VERIFIED |
| `build_process_topology` | `hermes_personal/runtime/processes.py` | `69` | VERIFIED |
| `Supervisor.run` | `hermes_personal/runtime/supervisor.py` | `477` | VERIFIED |
| `DefaultProcessRunner.start` | `hermes_personal/runtime/supervisor.py` | `124` | VERIFIED |
| `create_readiness_probe` | `hermes_personal/runtime/readiness.py` | `114` | VERIFIED |
| `ReadinessProbe` | `hermes_personal/runtime/readiness.py` | `55` | VERIFIED |
| `HermesTurnService` | `hermes_personal/orchestration/turn_service.py` | `74` | VERIFIED |
| `UpstreamAIAgentAdapter` | `hermes_personal/orchestration/upstream_agent.py` | `46` | VERIFIED |
| `EventRepository` | `hermes_personal/orchestration/event_repository.py` | `85` | VERIFIED |
| `SessionRepository` | `hermes_personal/sessions/repository.py` | `17` | VERIFIED |
| `IdentityRepository` | `hermes_personal/identity/repository.py` | `12` | VERIFIED |
| `WorkflowEngine` | `hermes_personal/workflows/engine.py` | `21` | VERIFIED |
| `Supervisor` | `hermes_personal/runtime/supervisor.py` | `169` | VERIFIED |
