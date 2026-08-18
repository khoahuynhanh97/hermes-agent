"""Repository consolidation and cleanup script for Hermes Agent."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(r"D:\work\hermes-agent").resolve()
DATA_ROOT = Path(r"D:\work\hermes-agent-data").resolve()
QUARANTINE_DIR = DATA_ROOT / "cleanup-quarantine" / f"quarantine-{int(time.time())}"

def ensure_dirs():
    (REPO_ROOT / "scripts" / "ops").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "scripts" / "dev").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "scripts" / "acceptance").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "scripts" / "acceptance" / "live").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "scripts" / "migrations").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "server").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "agent").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "hermes").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "tools").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "workers").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "integration").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "tests" / "acceptance").mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

def safe_remove_dir(p: Path):
    if p.exists() and p.is_dir() and REPO_ROOT in p.resolve().parents:
        print(f"Removing directory: {p}")
        shutil.rmtree(p, ignore_errors=True)

def safe_remove_file(p: Path):
    if p.exists() and p.is_file() and (REPO_ROOT in p.resolve().parents or p.resolve().parent == REPO_ROOT):
        print(f"Removing file: {p}")
        try:
            p.unlink()
        except Exception as e:
            print(f"Error removing {p}: {e}")

def quarantine_file(src: Path, reason: str, manifest: list):
    if src.exists() and src.is_file():
        dest = QUARANTINE_DIR / src.name
        print(f"Quarantining {src} -> {dest} (Reason: {reason})")
        size = src.stat().st_size
        shutil.move(str(src), str(dest))
        manifest.append({
            "original_path": str(src),
            "quarantine_path": str(dest),
            "size_bytes": size,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason
        })

def safe_move_file(src: Path, dest_dir: Path):
    if src.exists() and src.is_file():
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        print(f"Moving {src.name} -> {dest_dir.relative_to(REPO_ROOT)}")
        shutil.move(str(src), str(dest))

def phase2_remove_generated_artifacts():
    print("=== Phase 2: Removing generated artifacts ===")
    patterns = [
        ".pytest-*",
        ".tmp-*",
        "workhermes-agent.tmp-*",
        ".audit-pytest-*",
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".mypy_cache",
        ".ruff_cache",
    ]
    for item in REPO_ROOT.iterdir():
        if item.is_dir():
            for pat in patterns:
                if item.match(pat):
                    safe_remove_dir(item)
                    break

    # Remove all __pycache__ and *.pyc
    for pycache in REPO_ROOT.rglob("__pycache__"):
        if ".venv" not in pycache.parts and "node_modules" not in pycache.parts:
            safe_remove_dir(pycache)

    for pyc in REPO_ROOT.rglob("*.py[cod]"):
        if ".venv" not in pyc.parts and "node_modules" not in pyc.parts:
            safe_remove_file(pyc)

    tmp_fallback = REPO_ROOT / "scripts" / ".tmp_learning_fallback"
    safe_remove_dir(tmp_fallback)

def phase3_and_4_organize_root_and_scripts():
    print("=== Phase 3 & 4: Organizing root files and scripts ===")
    manifest = []

    # 1. Root temporary scripts to quarantine or move
    root_to_quarantine = [
        ("job.json", "temporary root job payload"),
        ("diagnose_errors.json", "temporary root diagnostics artifact"),
        ("ai_video_script_ugreen.md", "draft acceptance script document"),
        ("kickban_ugreen_video.md", "draft acceptance document"),
        ("storyboard_ugreen.json", "draft acceptance storyboard json"),
        ("video_script_ugreen.md", "draft acceptance video script"),
        ("telegram_bot.md", "temporary telegram bot documentation draft"),
        (".bytecode-fingerprint", "temporary build fingerprint"),
    ]
    for filename, reason in root_to_quarantine:
        quarantine_file(REPO_ROOT / filename, reason, manifest)

    # 2. Root scripts to move to scripts/ops/
    ops_scripts = [
        "backup_database.py",
        "export_knowledge.py",
        "export_approved_markdown.py",
        "build_obsidian_vault.py",
        "load_affiliate_csv.py",
        "create_ai_style_video.py",
        "create_video.py",
        "create_video_opencv.py",
        "start_bot.bat",
        "start_bot.ps1",
        "start_gui.bat",
        "start_web.bat",
        "start_telegram_and_worker.bat",
        "run_api_tests.bat",
    ]
    for s in ops_scripts:
        safe_move_file(REPO_ROOT / s, REPO_ROOT / "scripts" / "ops")

    # 3. Root scripts to move to scripts/migrations/
    migration_scripts = [
        "apply_full_affiliate_schema.py",
        "fix_affiliate_schema.py",
        "migrate_v2_to_v5.py",
    ]
    for s in migration_scripts:
        safe_move_file(REPO_ROOT / s, REPO_ROOT / "scripts" / "migrations")

    # 4. Root scripts to move to scripts/dev/
    dev_scripts = [
        "_check_packages.py",
        "check_all_affiliate.py",
        "check_errors.py",
        "check_schema_v1.py",
        "verify_affiliate_results.py",
        "verify_migration.py",
        "inspect_broken_sources.py",
        "filter_structure.py",
        "report_structure.py",
        "test_failed_urls.py",
        "test_worker.py",
    ]
    for s in dev_scripts:
        safe_move_file(REPO_ROOT / s, REPO_ROOT / "scripts" / "dev")

    # 5. Live / Paid Provider acceptance scripts
    live_scripts = [
        "test_vertex_ai.py",
        "test_vertex_image.py",
    ]
    for s in live_scripts:
        safe_move_file(REPO_ROOT / s, REPO_ROOT / "scripts" / "acceptance" / "live")

    # 6. Test scripts from root to tests/
    if (REPO_ROOT / "test_web_studio_api.py").exists():
        safe_move_file(REPO_ROOT / "test_web_studio_api.py", REPO_ROOT / "tests" / "server")

    # 7. Organize flat files inside scripts/ directory
    # Live acceptance
    scripts_live = [
        "pimg1_live_acceptance.py",
        "pimg1b_live_acceptance.py",
        "pvid1_live_acceptance.py",
        "pvid1b_live_acceptance.py",
        "tts1_live_acceptance.py",
        "setup_vertex_auth.py",
    ]
    for s in scripts_live:
        safe_move_file(REPO_ROOT / "scripts" / s, REPO_ROOT / "scripts" / "acceptance" / "live")

    # Migrations
    scripts_migrations = [
        "migrate_knowledge_to_sqlite.py",
        "vfe2e_migrate.py",
        "repair_knowledge_encoding.py",
        "docker_config_migrate.py",
    ]
    for s in scripts_migrations:
        safe_move_file(REPO_ROOT / "scripts" / s, REPO_ROOT / "scripts" / "migrations")

    # Acceptance scripts
    scripts_acceptance = [
        "build_30s_ugreen_video.py",
        "build_baseus_bowie_wm02_storyboard.py",
        "build_ugreen_custom_spot.py",
        "generate_ai_veo_scenes.py",
        "poll_and_assemble_veo_video.py",
        "recover_veo_scenes.py",
        "register_baseus_wm02_30s_campaign.py",
        "product_research_script.py",
        "script_quat_aecooly_typec.md",
        "ugreen_live_leg1.py",
        "ugreen_live_leg2.py",
        "ugreen_live_leg3.py",
        "ugreen_live_leg4.py",
        "ugreen_live_leg5.py",
        "ugreen_live_leg6.py",
        "vfe2e_leg1.py",
        "vfe2e_leg2.py",
        "vfe2e_leg3.py",
        "vfe2e_leg4.py",
        "vfe2e_leg5.py",
        "vfe2e_leg6.py",
        "vfe2e_verify.py",
        "verify_modernization_migration.py",
        "smoke_nemo_relay_shared_metrics.py",
    ]
    for s in scripts_acceptance:
        safe_move_file(REPO_ROOT / "scripts" / s, REPO_ROOT / "scripts" / "acceptance")

    # Ops scripts
    scripts_ops = [
        "doctor.py",
        "hermes_maintenance.py",
        "hermes_backup.py",
        "start_9router_local.ps1",
        "start_telegram_review_watcher.ps1",
        "start_tiktok_crawler_local.ps1",
        "setup_crawl4ai.ps1",
        "run_job_worker.py",
        "configure_canonical_runtime.py",
        "telegram_review_watcher.py",
        "agent_control.py",
        "docker_rebootstrap_nous_session.py",
        "install.cmd",
        "install.ps1",
        "install.sh",
        "kill_modal.sh",
        "run_tests.sh",
        "run_tests_parallel.py",
        "release.py",
        "render_prompt.py",
        "sync_and_listen.py",
        "sync_index_from_entries.py",
        "add_contributor.py",
    ]
    for s in scripts_ops:
        safe_move_file(REPO_ROOT / "scripts" / s, REPO_ROOT / "scripts" / "ops")

    # Dev scripts
    scripts_dev = [
        "analyze_livetest.py",
        "analyze_modules.py",
        "audit_pr_attribution.py",
        "benchmark_browser_eval.py",
        "build_model_catalog.py",
        "build_skills_index.py",
        "check-windows-footguns.py",
        "check_subprocess_stdin.py",
        "contributor_audit.py",
        "crawl4ai_pilot.py",
        "dev-sandbox.sh",
        "discord-voice-doctor.py",
        "ffmpeg_wrapper.py",
        "generate_conformance_vectors.py",
        "hermes-gateway",
        "hermes_assistant_cli.py",
        "hermes_code_agent.py",
        "hermes_patch.py",
        "hermes_repo_map.py",
        "hermes_tool.py",
        "hermes_verify.py",
        "install_psutil_android.py",
        "iso-certify.py",
        "keystroke_diagnostic.py",
        "lint_diff.py",
        "micro_compaction_report.py",
        "profile-tui.py",
        "recover_pending_knowledge.py",
        "run_scraper_pipeline.py",
        "sample_and_compress.py",
        "tool_search_livetest.py",
        "tool_search_livetest2.py",
        "tool_search_livetest_ue.py",
        "tool_search_livetest_ue_disc.py",
        "tool_search_livetest_ue_hard.py",
        "telegram_userbot.py",
        "affiliate_analysis_runner.py",
        "affiliate_research_worker.py",
        "capture-cage-terminal.sh",
        "LIVETEST_README.md",
    ]
    for s in scripts_dev:
        safe_move_file(REPO_ROOT / "scripts" / s, REPO_ROOT / "scripts" / "dev")

    # Any test_*.py inside scripts/ root -> move to tests/ or scripts/acceptance/
    for item in (REPO_ROOT / "scripts").iterdir():
        if item.is_file() and item.name.startswith("test_"):
            safe_move_file(item, REPO_ROOT / "scripts" / "acceptance")

    # Save quarantine manifest
    if manifest:
        manifest_path = QUARANTINE_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Quarantine manifest written to: {manifest_path}")

def main():
    ensure_dirs()
    phase2_remove_generated_artifacts()
    phase3_and_4_organize_root_and_scripts()
    print("Consolidation script completed successfully.")

if __name__ == "__main__":
    main()
