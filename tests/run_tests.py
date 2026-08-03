"""Run unit tests with compact terminal progress and a detailed file report."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIRECTORY = PROJECT_ROOT / "tests"
DEFAULT_REPORT = PROJECT_ROOT / "test-results" / "unit-tests.log"
PROGRESS_WIDTH = 30

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ProgressTestResult(unittest.TextTestResult):
    """Write normal unittest details to a file and aggregate progress to stdout."""

    _status_priority = {
        "passed": 0,
        "skipped": 1,
        "expected failure": 2,
        "failed": 3,
        "error": 4,
        "unexpected success": 5,
    }

    def __init__(
        self,
        stream: unittest.runner._WritelnDecorator,
        descriptions: bool,
        verbosity: int,
        *,
        progress_stream: TextIO,
        total: int,
    ) -> None:
        super().__init__(stream, descriptions, verbosity)
        self.progress_stream = progress_stream
        self.total = total
        self.completed = 0
        self.counts = {
            "passed": 0,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "expected failure": 0,
            "unexpected success": 0,
        }
        self._current_status = "passed"

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._current_status = "passed"
        super().startTest(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:
        super().stopTest(test)
        self.completed += 1
        self.counts[self._current_status] += 1
        self._draw_progress()

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type, BaseException, object]) -> None:
        self._mark("failed")
        super().addFailure(test, err)

    def addError(self, test: unittest.case.TestCase, err: tuple[type, BaseException, object]) -> None:
        self._mark("error")
        super().addError(test, err)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        self._mark("skipped")
        super().addSkip(test, reason)

    def addExpectedFailure(
        self,
        test: unittest.case.TestCase,
        err: tuple[type, BaseException, object],
    ) -> None:
        self._mark("expected failure")
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        self._mark("unexpected success")
        super().addUnexpectedSuccess(test)

    def addSubTest(
        self,
        test: unittest.case.TestCase,
        subtest: unittest.case.TestCase,
        err: tuple[type, BaseException, object] | None,
    ) -> None:
        if err is not None:
            exception_type = err[0]
            self._mark("failed" if issubclass(exception_type, test.failureException) else "error")
        super().addSubTest(test, subtest, err)

    def _mark(self, status: str) -> None:
        if self._status_priority[status] >= self._status_priority[self._current_status]:
            self._current_status = status

    def _draw_progress(self) -> None:
        ratio = self.completed / self.total if self.total else 1.0
        filled = round(PROGRESS_WIDTH * ratio)
        bar = "#" * filled + "-" * (PROGRESS_WIDTH - filled)
        summary = (
            f"passed={self.counts['passed']} "
            f"failed={self.counts['failed']} "
            f"errors={self.counts['error']} "
            f"skipped={self.counts['skipped']}"
        )
        self.progress_stream.write(
            f"\rTests [{bar}] {self.completed}/{self.total} | {summary}"
        )
        self.progress_stream.flush()


def _report_path() -> Path:
    configured = os.environ.get("JOB_AGENT_TEST_REPORT")
    if not configured:
        return DEFAULT_REPORT
    path = Path(configured).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(TEST_DIRECTORY),
        pattern="test_*.py",
    )
    total = suite.countTestCases()
    report_path = _report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8") as report:
        report.write(
            "Job Agent unit-test report\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
            f"Tests discovered: {total}\n\n"
        )

        def result_factory(
            stream: unittest.runner._WritelnDecorator,
            descriptions: bool,
            verbosity: int,
        ) -> ProgressTestResult:
            return ProgressTestResult(
                stream,
                descriptions,
                verbosity,
                progress_stream=sys.stdout,
                total=total,
            )

        runner = unittest.TextTestRunner(
            stream=report,
            verbosity=2,
            resultclass=result_factory,
            buffer=True,
        )
        result = runner.run(suite)

    if total == 0:
        print("Tests [------------------------------] 0/0 | no tests discovered")
    else:
        print()
    print(f"Detailed report: {report_path}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
