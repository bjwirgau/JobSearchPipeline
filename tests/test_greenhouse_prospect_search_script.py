"""Tests for the scheduled Greenhouse prospect-search runner."""

from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_greenhouse_prospect_search.sh"
MATCHER_PATH = PROJECT_ROOT / "scripts" / "run_job_matcher.sh"
RESUME_GENERATOR_PATH = PROJECT_ROOT / "scripts" / "run_resume_generator.sh"
DEPLOY_PATH = PROJECT_ROOT / "scripts" / "deploy.sh"
INSTALLER_PATH = PROJECT_ROOT / "scripts" / "install_cron_jobs.sh"


class GreenhouseProspectSearchScriptTests(unittest.TestCase):
    def test_script_is_executable_and_valid_shell(self) -> None:
        self.assertTrue(SCRIPT_PATH.stat().st_mode & stat.S_IXUSR)
        result = subprocess.run(
            ["sh", "-n", str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_script_only_discovers_and_stores_greenhouse_jobs(self) -> None:
        script = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("--source greenhouse", script)
        self.assertNotIn("--unmatched-only", script)
        self.assertNotIn("--match-prospects", script)
        self.assertIn("greenhouse-prospect-search.lock", script)
        self.assertIn("greenhouse-prospect-search.log", script)
        self.assertIn("JOB_AGENT_GREENHOUSE_SEARCH_LIMIT", script)
        self.assertIn("JOB_AGENT_GREENHOUSE_BOARD_LIMIT", script)
        self.assertIn("--greenhouse-board-limit", script)

    def test_matcher_is_executable_rate_limited_and_valid_shell(self) -> None:
        self.assertTrue(MATCHER_PATH.stat().st_mode & stat.S_IXUSR)
        result = subprocess.run(
            ["sh", "-n", str(MATCHER_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        script = MATCHER_PATH.read_text(encoding="utf-8")
        self.assertIn("--match-prospects", script)
        self.assertIn("--match-limit", script)
        self.assertIn("job-agent-job-matcher.lock", script)
        self.assertIn("job-matcher.log", script)
        self.assertIn('"$match_limit" -gt 15', script)

    def test_cron_installer_manages_all_project_jobs(self) -> None:
        self.assertTrue(INSTALLER_PATH.stat().st_mode & stat.S_IXUSR)
        result = subprocess.run(
            ["sh", "-n", str(INSTALLER_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        script = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("run_greenhouse_crawler.sh", script)
        self.assertIn("run_greenhouse_prospect_search.sh", script)
        self.assertIn("run_job_matcher.sh", script)
        self.assertIn("run_resume_generator.sh", script)
        self.assertIn("JOB_AGENT_MATCHER_CRON_SCHEDULE:-* * * * *", script)
        self.assertIn(
            "JOB_AGENT_RESUME_GENERATOR_CRON_SCHEDULE:-* * * * *",
            script,
        )
        self.assertIn("JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT", script)
        self.assertIn("job-agent managed cron jobs", script)

    def test_resume_generator_is_executable_bounded_and_valid_shell(self) -> None:
        self.assertTrue(RESUME_GENERATOR_PATH.stat().st_mode & stat.S_IXUSR)
        result = subprocess.run(
            ["sh", "-n", str(RESUME_GENERATOR_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        script = RESUME_GENERATOR_PATH.read_text(encoding="utf-8")
        self.assertIn("--generate-matched-resumes", script)
        self.assertIn("--resume-limit", script)
        self.assertIn("--resume-format", script)
        self.assertIn("job-agent-resume-generator.lock", script)
        self.assertIn("resume-generator.log", script)
        self.assertIn('"$resume_limit" -gt 100', script)

    def test_deployment_waits_for_the_resume_generator_lock(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(DEPLOY_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        script = DEPLOY_PATH.read_text(encoding="utf-8")
        self.assertIn("job-agent-resume-generator.lock", script)
        self.assertIn("Timed out waiting for the resume generator", script)


if __name__ == "__main__":
    unittest.main()
