"""Selenium application filling tests with a browser-driver fake."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from browser import (
    ApplicationBrowserDisabledError,
    SeleniumApplicationBrowser,
)


class FakeElement:
    def __init__(
        self,
        tag_name: str,
        label: str,
        *,
        input_type: str = "text",
        required: bool = False,
        value: str = "",
    ) -> None:
        self.tag_name = tag_name
        self.label = label
        self.text = label if tag_name in {"button", "a"} else ""
        self.attrs = {
            "type": input_type,
            "required": "required" if required else None,
            "value": value,
            "name": label.casefold().replace(" ", "-"),
        }
        self.selected = False
        self.clicked = False
        self.sent: list[str] = []
        self.cleared = False

    def get_attribute(self, name: str) -> object:
        return self.attrs.get(name)

    def is_displayed(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True

    def is_selected(self) -> bool:
        return self.selected

    def clear(self) -> None:
        self.cleared = True

    def send_keys(self, value: str) -> None:
        self.sent.append(value)

    def click(self) -> None:
        self.clicked = True
        if self.attrs.get("type") == "checkbox":
            self.selected = not self.selected

    def find_elements(self, by: str, value: str) -> list["FakeElement"]:
        return []


class FakeSwitchTo:
    def default_content(self) -> None:
        return None

    def frame(self, frame: object) -> None:
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.current_url = ""
        self.switch_to = FakeSwitchTo()
        self.timeout = 0.0
        self.implicit_timeout = 0.0
        self.quit_called = False
        self.text_field = FakeElement("input", "First Name", required=True)
        self.resume_field = FakeElement(
            "input",
            "Resume / CV",
            input_type="file",
            required=True,
        )
        self.submit = FakeElement(
            "input",
            "Submit Application",
            input_type="submit",
            value="Submit Application",
        )
        self.next = FakeElement("button", "Next")

    def set_page_load_timeout(self, value: float) -> None:
        self.timeout = value

    def implicitly_wait(self, value: float) -> None:
        self.implicit_timeout = value

    def get(self, url: str) -> None:
        self.current_url = url

    def quit(self) -> None:
        self.quit_called = True

    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        if value == "iframe, frame":
            return []
        if value == "input, textarea, select":
            return [self.text_field, self.resume_field, self.submit]
        if value.startswith("button, input[type='button']"):
            return [self.submit, self.next]
        return []

    def execute_script(self, script: str, *arguments: object) -> object:
        if "const labels" in script:
            return arguments[0].label
        if "const controls" in script:
            return 1
        if "closest('form')" in script:
            return False
        return ""


class SeleniumApplicationBrowserTests(unittest.TestCase):
    def test_requires_explicit_enablement(self) -> None:
        browser = SeleniumApplicationBrowser(
            enabled=False,
            driver_factory=FakeDriver,
        )

        with self.assertRaisesRegex(
            ApplicationBrowserDisabledError,
            "disabled",
        ):
            browser.open("https://example.com/jobs/1")

    def test_fills_text_uploads_resume_and_never_clicks_submit(self) -> None:
        driver = FakeDriver()
        browser = SeleniumApplicationBrowser(
            enabled=True,
            driver_factory=lambda: driver,
        )
        session = browser.open("https://example.com/jobs/1")
        fields = session.inspect_fields()
        self.assertEqual([field.label for field in fields], ["First Name", "Resume / CV"])

        with tempfile.TemporaryDirectory() as directory:
            resume = Path(directory) / "resume.docx"
            resume.write_bytes(b"resume")
            result = session.fill_fields(
                {fields[0].field_id: "Example"},
                resume_path=resume,
            )

        self.assertTrue(result.complete)
        self.assertTrue(result.resume_uploaded)
        self.assertEqual(driver.text_field.sent, ["Example"])
        self.assertEqual(driver.resume_field.sent, [str(resume.resolve())])
        self.assertEqual(session.disable_submission(), 1)
        self.assertTrue(session.advance())
        self.assertTrue(driver.next.clicked)
        self.assertFalse(driver.submit.clicked)
        session.close()
        self.assertTrue(driver.quit_called)


if __name__ == "__main__":
    unittest.main()
