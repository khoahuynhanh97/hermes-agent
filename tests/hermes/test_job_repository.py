from __future__ import annotations

import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from hermes.db import Database


class JobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.database.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enqueue_claim_and_complete(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("job-1", 42, "learning", {"source": {"value": "note"}}, chat_id=420)

        claimed = jobs.claim_next()

        self.assertEqual(claimed["id"], "job-1")
        self.assertEqual(claimed["state"], "running")
        self.assertEqual(claimed["payload"]["source"]["value"], "note")
        completed = jobs.complete("job-1", {"summary": "done"})
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["result"]["summary"], "done")

    def test_claim_is_atomic_and_owner_scoped(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("job-1", 42, "learning", {"n": 1})
        jobs.enqueue("job-2", 99, "learning", {"n": 2})

        first = jobs.claim_next()
        second = jobs.claim_next()
        third = jobs.claim_next()

        self.assertEqual({first["id"], second["id"]}, {"job-1", "job-2"})
        self.assertIsNone(third)
        self.assertEqual([row["id"] for row in jobs.list_jobs(owner_user_id=42)], ["job-1"])

    def test_claim_next_filters_by_type_without_claiming_legacy_jobs(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("legacy", 42, "learning", {"n": 1})
        jobs.enqueue("affiliate", 42, "affiliate_product_research", {"n": 2})

        claimed = jobs.claim_next("affiliate_product_research")

        self.assertEqual(claimed["id"], "affiliate")
        self.assertEqual(jobs.get("legacy")["state"], "queued")
        self.assertEqual(jobs.claim_next()["id"], "legacy")

    def test_legacy_claim_never_takes_dedicated_affiliate_job(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("affiliate-only", "42", "affiliate_product_research", {})

        self.assertIsNone(jobs.claim_next())
        self.assertEqual(
            jobs.claim_next("affiliate_product_research")["id"], "affiliate-only"
        )

    def test_retry_is_bounded_and_manual_retry_requires_owner(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("job-1", 42, "learning", {"n": 1}, max_attempts=2)
        jobs.claim_next()
        first_failure = jobs.fail("job-1", "temporary", retryable=True)
        self.assertEqual(first_failure["state"], "queued")

        jobs.claim_next()
        final_failure = jobs.fail("job-1", "still broken", retryable=True)
        self.assertEqual(final_failure["state"], "failed")
        self.assertIsNone(jobs.retry("job-1", owner_user_id=99))
        self.assertEqual(jobs.retry("job-1", owner_user_id=42)["state"], "queued")

    def test_cancel_is_cooperative_for_running_job(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("queued", 42, "learning", {})
        self.assertEqual(jobs.cancel("queued", 42)["state"], "cancelled")

        jobs.enqueue("running", 42, "learning", {})
        jobs.claim_next()
        requested = jobs.cancel("running", 42)
        self.assertEqual(requested["state"], "running")
        self.assertTrue(requested["cancel_requested"])
        self.assertTrue(jobs.is_cancel_requested("running"))
        self.assertEqual(jobs.acknowledge_cancel("running")["state"], "cancelled")

    def test_restart_recovery_requeues_running_jobs(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("job-1", 42, "learning", {})
        jobs.claim_next()

        recovered = jobs.recover_interrupted()

        self.assertEqual(recovered, ["job-1"])
        self.assertEqual(jobs.get("job-1")["state"], "queued")

    def test_terminal_job_history_can_be_pruned_without_touching_active_jobs(self) -> None:
        from hermes.jobs import JobRepository

        jobs = JobRepository(self.database)
        jobs.enqueue("old", 42, "learning", {})
        jobs.claim_next()
        jobs.complete("old", {})
        jobs.enqueue("active", 42, "learning", {})
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE jobs SET completed_at = '2020-01-01T00:00:00+00:00' WHERE id = 'old'"
            )

        removed = jobs.prune_terminal("2025-01-01T00:00:00+00:00")

        self.assertEqual(removed, 1)
        self.assertIsNone(jobs.get("old"))
        self.assertIsNotNone(jobs.get("active"))

    def test_agent_job_manager_uses_sqlite_without_manifest_mirror(self) -> None:
        from core.agent_jobs import AgentJobManager

        class FakeProjectManager:
            def __init__(self, root: Path):
                self.root = root
                self.metadata = {}

            def initialize_project(self, name: str):
                slug = "learning-source"
                path = self.root / slug
                path.mkdir(parents=True, exist_ok=True)
                return str(path), slug

            def get_project_folders(self, slug: str):
                path = self.root / slug
                path.mkdir(parents=True, exist_ok=True)
                return {"root": str(path)}

            def get_metadata(self, slug: str):
                return self.metadata.get(slug, {})

            def save_metadata(self, slug: str, value: dict):
                self.metadata[slug] = value

        jobs_root = Path(self.temp_dir.name) / "legacy-jobs"
        project_manager = FakeProjectManager(Path(self.temp_dir.name) / "projects")
        with patch.dict(
            environ,
            {
                "HERMES_STORAGE_BACKEND": "sqlite",
                "HERMES_DB_PATH": str(self.database.path),
            },
        ):
            manager = AgentJobManager(project_manager=project_manager, jobs_root=jobs_root)
            created = manager.create_job(
                "A source note",
                source_kind="text",
                created_by="telegram",
                telegram_info={"user_id": 42, "chat_id": 420},
                job_type="learn_knowledge",
                tasks=["learn_knowledge"],
            )
            claimed = manager.claim_next_job()

        self.assertTrue(manager.uses_sqlite)
        self.assertEqual(claimed["job_id"], created["job_id"])
        self.assertFalse((jobs_root / "inbox" / f"{created['job_id']}.json").exists())
        self.assertNotIn("manifest", created)

    def test_worker_claims_sqlite_job_without_reading_legacy_inbox(self) -> None:
        from core.job_watcher import JobWorker

        job = {
            "job_id": "job-sqlite",
            "target": {"project_slug": "learning", "output_dir": self.temp_dir.name},
            "source": {"value": "note"},
        }

        class FakeManager:
            uses_sqlite = True

            def __init__(self):
                self.completed = None

            def claim_next_job(self):
                return job

            def is_cancel_requested(self, job_id):
                return False

            def complete_job(self, job_id, summary="", files_created=None):
                self.completed = (job_id, summary, files_created)

        worker = object.__new__(JobWorker)
        worker.manager = FakeManager()
        worker.task_queue = None
        worker.execute_job_tasks = lambda value: (["summary_analysis.md"], "done")

        with patch("core.job_watcher.logger"):
            processed = worker.process_next_job()

        self.assertTrue(processed)
        self.assertEqual(
            worker.manager.completed,
            ("job-sqlite", "done", ["summary_analysis.md"]),
        )


if __name__ == "__main__":
    unittest.main()
