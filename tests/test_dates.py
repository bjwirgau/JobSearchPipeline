"""Shared date formatting tests."""

from __future__ import annotations

import unittest

from utils.dates import format_month_year


class ResumeDateFormattingTests(unittest.TestCase):
    def test_formats_supported_resume_dates_as_month_and_year(self) -> None:
        self.assertEqual(format_month_year("2025-08"), "August 2025")
        self.assertEqual(format_month_year("2025-08-17"), "August 2025")
        self.assertEqual(format_month_year("Aug 2025"), "August 2025")
        self.assertEqual(format_month_year("august 2025"), "August 2025")
        self.assertEqual(
            format_month_year("current", allow_present=True),
            "Present",
        )

    def test_rejects_dates_without_month_precision(self) -> None:
        for value in ("2025", "2025-13", "Present"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                "resume date must use",
            ):
                format_month_year(value)


if __name__ == "__main__":
    unittest.main()
