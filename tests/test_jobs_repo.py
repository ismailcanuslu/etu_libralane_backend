import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "jobs.db"))
os.environ.setdefault("WORKSPACE_ROOT", os.path.join(_TMP, "workspace"))

from app.core.config import get_settings
from app.core.db import init_db
from app.models.job import JobStatus
from app.services import chat_history_service, jobs_repo


class JobsRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        init_db()

    def test_create_job_is_usable_after_session_close(self) -> None:
        job = jobs_repo.create_job(
            project_id="demo-project",
            action="smoke-test",
            image="librelane/runner:basic",
            command='["true"]',
        )
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertTrue(job.id)
        self.assertEqual(job.action, "smoke-test")


class ChatHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        init_db()

    def test_save_and_load_roundtrip(self) -> None:
        chat_history_service.save_project_history(
            "proj-a",
            [
                {
                    "id": "m1",
                    "role": "user",
                    "content": "merhaba",
                    "timestamp": "2024-01-01T12:00:00Z",
                }
            ],
        )
        msgs = chat_history_service.get_messages_for_project("proj-a")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["id"], "m1")
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "merhaba")

    def test_replace_clears_previous(self) -> None:
        chat_history_service.save_project_history("proj-b", [{"id": "1", "role": "user", "content": "a", "timestamp": "2024-01-01T00:00:00Z"}])
        chat_history_service.save_project_history("proj-b", [])
        self.assertEqual(chat_history_service.get_messages_for_project("proj-b"), [])


if __name__ == "__main__":
    unittest.main()
