"""Tests for the scheduled Greenhouse prospect-search runner."""

from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_greenhouse_prospect_search.sh"
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

    def test_script_uses_stored_greenhouse_source_and_skips_scored_jobs(self) -> None:
        script = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("--source greenhouse", script)
        self.assertIn("--unmatched-only", script)
        self.assertIn("greenhouse-prospect-search.lock", script)
        self.assertIn("greenhouse-prospect-search.log", script)
        self.assertIn("JOB_AGENT_GREENHOUSE_SEARCH_LIMIT", script)

    def test_cron_installer_manages_both_project_jobs(self) -> None:
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
        self.assertIn("job-agent managed cron jobs", script)


if __name__ == "__main__":
    unittest.main()
