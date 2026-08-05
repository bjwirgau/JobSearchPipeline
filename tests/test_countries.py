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


if __name__ == "__main__":
    unittest.main()
