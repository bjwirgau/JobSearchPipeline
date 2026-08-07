"""Tests for the guarded AWS-to-local database copy command."""

from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "copy_aws_database.sh"


class CopyAwsDatabaseScriptTests(unittest.TestCase):
    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT_PATH.stat().st_mode & stat.S_IXUSR)

    def test_help_documents_guarded_replacement(self) -> None:
        result = subprocess.run(
            ["bash", str(SCRIPT_PATH), "--help"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--replace-local-database", result.stdout)
        self.assertIn("JOB_AGENT_AWS_MYSQL_PASSWORD", result.stdout)

    def test_replacement_flag_is_required_before_dependencies_are_checked(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT_PATH),
                "--instance-id",
                "i-0123456789abcdef0",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--replace-local-database", result.stderr)


if __name__ == "__main__":
    unittest.main()
