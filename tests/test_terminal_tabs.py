import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "jobs.db"))
os.environ.setdefault("WORKSPACE_ROOT", os.path.join(_TMP, "workspace"))

from app.core.config import get_settings
from app.core.db import init_db
from app.services import jobs_repo
from app.services.terminal_tabs import registry


class TerminalTabsTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        init_db()
        registry._tabs.clear()

    def test_open_list_and_close_tab(self) -> None:
        job = jobs_repo.create_job("demo", "smoke-test", "efabless/openlane:ci2504-dev-amd64", "[]")
        registry.open(job.id, job.project_id, job.action)

        tabs = registry.list_open(project_id="demo")
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0].job_id, job.id)

        self.assertTrue(registry.close(job.id))
        self.assertEqual(registry.list_open(project_id="demo"), [])

    def test_open_is_idempotent_for_same_job(self) -> None:
        job = jobs_repo.create_job("demo", "lint", "efabless/openlane:ci2504-dev-amd64", "[]")
        first = registry.open(job.id, job.project_id, job.action)
        second = registry.open(job.id, job.project_id, job.action)
        self.assertEqual(first.opened_at, second.opened_at)
        self.assertEqual(len(registry.list_open()), 1)


if __name__ == "__main__":
    unittest.main()
