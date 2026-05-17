import unittest
from unittest.mock import patch

from app.models.job import Job, JobStatus
from app.services.artifact_paths import (
    job_artifacts_base,
    job_artifacts_prefix,
    workspace_artifact_prefixes,
)


class ArtifactPathsTests(unittest.TestCase):
    def test_workspace_exclude_both_prefixes(self) -> None:
        prefixes = workspace_artifact_prefixes()
        self.assertIn("_jobs/", prefixes)
        self.assertIn("_autonom_jobs/", prefixes)

    def test_autonom_job_artifacts_prefix(self) -> None:
        job = Job(
            project_id="p1",
            action="synthesis",
            image="img",
            command="[]",
            channel="autonom",
            status=JobStatus.QUEUED,
        )
        job.id = "abc123"
        with patch("app.services.artifact_paths.get_settings") as mock_settings:
            mock_settings.return_value = type(
                "S",
                (),
                {
                    "jobs_artifacts_prefix": "_jobs",
                    "autonom_jobs_artifacts_prefix": "_autonom_jobs",
                },
            )()
            self.assertEqual(job_artifacts_prefix(job), "_autonom_jobs/abc123")
            self.assertEqual(job_artifacts_base(channel="autonom"), "_autonom_jobs")
            self.assertEqual(job_artifacts_base(channel="default"), "_jobs")


if __name__ == "__main__":
    unittest.main()
