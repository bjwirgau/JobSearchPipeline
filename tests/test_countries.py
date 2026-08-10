"""Country eligibility parsing and configuration tests."""

from __future__ import annotations

import unittest

from config import Settings
from utils.countries import country_codes_from_text, remote_country_is_eligible


class CountryEligibilityTests(unittest.TestCase):
    def test_extracts_countries_regions_and_worldwide_access(self) -> None:
        self.assertEqual(country_codes_from_text("Remote - USA"), ("us",))
        self.assertEqual(country_codes_from_text("Canada or US"), ("ca", "us"))
        self.assertEqual(country_codes_from_text("Anywhere in the U.S."), ("us",))
        self.assertIn("us", country_codes_from_text("North America"))
        self.assertEqual(country_codes_from_text("Worldwide"), ("*",))

    def test_unknown_remote_location_is_not_country_eligible(self) -> None:
        self.assertTrue(remote_country_is_eligible("us", ("*",), "Worldwide"))
        self.assertTrue(remote_country_is_eligible("us", (), "Remote - United States"))
        self.assertFalse(remote_country_is_eligible("us", ("ca",), "Remote - Canada"))
        self.assertFalse(remote_country_is_eligible("us", (), "Remote"))

    def test_remote_country_setting_uses_two_letter_codes(self) -> None:
        settings = Settings.from_env({"JOB_AGENT_REMOTE_COUNTRY": "US"})

        self.assertEqual(settings.remote_country, "us")
        with self.assertRaisesRegex(ValueError, "two-letter country code"):
            Settings.from_env({"JOB_AGENT_REMOTE_COUNTRY": "USA"})

    def test_mysql_settings_are_loaded_and_password_is_hidden(self) -> None:
        settings = Settings.from_env(
            {
                "JOB_AGENT_MYSQL_HOST": "mysql.internal",
                "JOB_AGENT_MYSQL_PORT": "3307",
                "JOB_AGENT_MYSQL_DATABASE": "job_agent_test",
                "JOB_AGENT_MYSQL_USER": "test_user",
                "JOB_AGENT_MYSQL_PASSWORD": "secret",
                "JOB_AGENT_MYSQL_CONNECT_TIMEOUT": "4",
            }
        )

        self.assertEqual(settings.mysql_host, "mysql.internal")
        self.assertEqual(settings.mysql_port, 3307)
        self.assertEqual(settings.mysql_database, "job_agent_test")
        self.assertEqual(settings.mysql_user, "test_user")
        self.assertEqual(settings.mysql_password, "secret")
        self.assertEqual(settings.mysql_connect_timeout, 4)
        self.assertNotIn("secret", repr(settings))

    def test_company_crawler_settings_are_validated(self) -> None:
        settings = Settings.from_env(
            {
                "JOB_AGENT_COMPANY_CRAWLER_ENABLED": "true",
                "JOB_AGENT_COMPANY_CRAWLER_SCAN_LIMIT": "7500",
                "JOB_AGENT_COMPANY_CRAWLER_CONCURRENCY": "4",
                "JOB_AGENT_COMPANY_CRAWLER_REQUEST_DELAY_SECONDS": "2.5",
                "JOB_AGENT_COMPANY_CRAWLER_FAILED_RETRY_HOURS": "12",
            }
        )

        self.assertTrue(settings.company_crawler_enabled)
        self.assertEqual(settings.company_crawler_scan_limit, 7500)
        self.assertEqual(settings.company_crawler_concurrency, 4)
        self.assertEqual(settings.company_crawler_request_delay_seconds, 2.5)
        self.assertEqual(settings.company_crawler_failed_retry_hours, 12)
        with self.assertRaisesRegex(ValueError, "between 1 and 20"):
            Settings.from_env(
                {"JOB_AGENT_COMPANY_CRAWLER_CONCURRENCY": "21"}
            )
        with self.assertRaisesRegex(ValueError, "FAILED_RETRY_HOURS"):
            Settings.from_env(
                {"JOB_AGENT_COMPANY_CRAWLER_FAILED_RETRY_HOURS": "0"}
            )

    def test_gemini_matching_settings_are_validated(self) -> None:
        settings = Settings.from_env(
            {
                "GEMINI_API_KEY": "secret",
                "JOB_AGENT_GEMINI_MODEL": "gemini-3.5-flash-lite",
                "JOB_AGENT_GEMINI_TIMEOUT_SECONDS": "45",
                "JOB_AGENT_MATCHING_CONCURRENCY": "3",
                "JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN": "10",
                "JOB_AGENT_RESUME_CANDIDATE_THRESHOLD": "0.9",
                "JOB_AGENT_RESUME_GENERATION_MODEL": "gpt-5.4",
                "OPENAI_API_KEY": "openai-secret",
                "JOB_AGENT_RESUME_GENERATION_TIMEOUT_SECONDS": "90",
                "JOB_AGENT_RESUME_GENERATION_MAX_OUTPUT_TOKENS": "5000",
                "JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT": "3",
                "JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT": "both",
                "JOB_AGENT_APPLICATION_BROWSER_ENABLED": "true",
                "JOB_AGENT_APPLICATION_BROWSER_HEADLESS": "true",
                "JOB_AGENT_APPLICATION_BROWSER_TIMEOUT_SECONDS": "20",
                "JOB_AGENT_APPLICATION_MAX_STEPS": "5",
            }
        )

        self.assertEqual(settings.gemini_model, "gemini-3.5-flash-lite")
        self.assertEqual(settings.gemini_timeout_seconds, 45)
        self.assertEqual(settings.matching_concurrency, 3)
        self.assertEqual(settings.matching_max_requests_per_run, 10)
        self.assertEqual(settings.resume_candidate_threshold, 0.9)
        self.assertEqual(settings.resume_generation_model, "gpt-5.4")
        self.assertEqual(settings.openai_api_key, "openai-secret")
        self.assertEqual(settings.resume_generation_timeout_seconds, 90)
        self.assertEqual(settings.resume_generation_max_output_tokens, 5000)
        self.assertEqual(settings.resume_generation_batch_limit, 3)
        self.assertEqual(settings.resume_generation_batch_format, "both")
        self.assertTrue(settings.application_browser_enabled)
        self.assertTrue(settings.application_browser_headless)
        self.assertEqual(settings.application_browser_timeout_seconds, 20)
        self.assertEqual(settings.application_max_steps, 5)
        self.assertNotIn("secret", repr(settings))
        with self.assertRaisesRegex(ValueError, "MATCHING_CONCURRENCY"):
            Settings.from_env({"JOB_AGENT_MATCHING_CONCURRENCY": "21"})
        with self.assertRaisesRegex(ValueError, "MATCHING_MAX_REQUESTS_PER_RUN"):
            Settings.from_env({"JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN": "16"})
        with self.assertRaisesRegex(ValueError, "RESUME_CANDIDATE_THRESHOLD"):
            Settings.from_env({"JOB_AGENT_RESUME_CANDIDATE_THRESHOLD": "1"})
        with self.assertRaisesRegex(ValueError, "RESUME_GENERATION_MODEL"):
            Settings.from_env({"JOB_AGENT_RESUME_GENERATION_MODEL": ""})
        with self.assertRaisesRegex(ValueError, "RESUME_GENERATION_TIMEOUT_SECONDS"):
            Settings.from_env({"JOB_AGENT_RESUME_GENERATION_TIMEOUT_SECONDS": "0"})
        with self.assertRaisesRegex(ValueError, "RESUME_GENERATION_MAX_OUTPUT_TOKENS"):
            Settings.from_env({"JOB_AGENT_RESUME_GENERATION_MAX_OUTPUT_TOKENS": "0"})
        with self.assertRaisesRegex(ValueError, "RESUME_GENERATION_BATCH_LIMIT"):
            Settings.from_env({"JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT": "101"})
        with self.assertRaisesRegex(ValueError, "RESUME_GENERATION_BATCH_FORMAT"):
            Settings.from_env({"JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT": "pdf"})
        with self.assertRaisesRegex(ValueError, "APPLICATION_BROWSER_TIMEOUT_SECONDS"):
            Settings.from_env({"JOB_AGENT_APPLICATION_BROWSER_TIMEOUT_SECONDS": "0"})
        with self.assertRaisesRegex(ValueError, "APPLICATION_MAX_STEPS"):
            Settings.from_env({"JOB_AGENT_APPLICATION_MAX_STEPS": "16"})

    def test_greenhouse_board_limit_is_validated(self) -> None:
        settings = Settings.from_env(
            {
                "JOB_AGENT_GREENHOUSE_BOARD_LIMIT": "10",
                "JOB_AGENT_GREENHOUSE_SCRAPER_ENABLED": "false",
                "JOB_AGENT_GREENHOUSE_SCRAPER_CONCURRENCY": "3",
            }
        )

        self.assertEqual(settings.greenhouse_board_limit, 10)
        self.assertFalse(settings.greenhouse_scraper_enabled)
        self.assertEqual(settings.greenhouse_scraper_concurrency, 3)
        with self.assertRaisesRegex(ValueError, "GREENHOUSE_BOARD_LIMIT"):
            Settings.from_env({"JOB_AGENT_GREENHOUSE_BOARD_LIMIT": "0"})
        with self.assertRaisesRegex(ValueError, "SCRAPER_CONCURRENCY"):
            Settings.from_env(
                {"JOB_AGENT_GREENHOUSE_SCRAPER_CONCURRENCY": "21"}
            )


if __name__ == "__main__":
    unittest.main()
