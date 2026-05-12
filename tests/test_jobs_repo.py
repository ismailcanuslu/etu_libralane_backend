import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "jobs.db"))
os.environ.setdefault("WORKSPACE_ROOT", os.path.join(_TMP, "workspace"))

from app.core.config import get_settings
from app.core.db import init_db
from app.models.job import JobStatus
from app.services import jobs_repo


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


if __name__ == "__main__":
    unittest.main()
