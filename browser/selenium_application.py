"""Review-only Selenium form discovery and filling with no submission action."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from models import (
    ApplicationFieldKind,
    ApplicationFillResult,
    ApplicationFormField,
)
from utils.text import normalize_text


class ApplicationBrowserDisabledError(RuntimeError):
    pass


class ApplicationBrowserDependencyError(RuntimeError):
    pass


class ApplicationBrowserNavigationError(RuntimeError):
    pass


class ApplicationBrowserSession(Protocol):
    @property
    def current_url(self) -> str: ...

    def inspect_fields(self) -> tuple[ApplicationFormField, ...]: ...

    def fill_fields(
        self,
        answers: Mapping[str, str],
        *,
        resume_path: Path,
    ) -> ApplicationFillResult: ...

    def open_application_form(self) -> bool: ...

    def advance(self) -> bool: ...

    def disable_submission(self) -> int: ...

    def close(self) -> None: ...


class ApplicationBrowser(Protocol):
    def open(self, url: str) -> ApplicationBrowserSession: ...


@dataclass(slots=True)
class _FieldTarget:
    field: ApplicationFormField
    frame_path: tuple[int, ...]
    elements: tuple[Any, ...]
    option_labels: tuple[str, ...] = ()


class SeleniumApplicationBrowser:
    def __init__(
        self,
        *,
        enabled: bool = False,
        headless: bool = False,
        timeout_seconds: float = 30.0,
        user_agent: str = "JobAgent/0.3 (+review-only-application-filling)",
        driver_factory: Any | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("application browser timeout must be greater than zero")
        self._enabled = enabled
        self._headless = headless
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._driver_factory = driver_factory

    def open(self, url: str) -> "SeleniumApplicationSession":
        if not self._enabled:
            raise ApplicationBrowserDisabledError(
                "application browser automation is disabled"
            )
        if not url.startswith(("https://", "http://")):
            raise ValueError("application URL must use HTTP or HTTPS")
        driver = self._create_driver()
        try:
            driver.set_page_load_timeout(self._timeout_seconds)
            driver.implicitly_wait(min(self._timeout_seconds, 10))
            driver.get(url)
        except Exception as error:
            driver.quit()
            raise ApplicationBrowserNavigationError(
                f"could not open application URL: {type(error).__name__}: {error}"
            ) from error
        return SeleniumApplicationSession(
            driver,
            timeout_seconds=self._timeout_seconds,
        )

    def _create_driver(self) -> Any:
        if self._driver_factory is not None:
            return self._driver_factory()
        try:
            from selenium import webdriver
        except ImportError as error:
            raise ApplicationBrowserDependencyError(
                "install Selenium support with: pip install -e '.[browser]'"
            ) from error
        options = webdriver.ChromeOptions()
        if self._headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={self._user_agent}")
        return webdriver.Chrome(options=options)


class SeleniumApplicationSession:
    _IGNORED_INPUT_TYPES = {
        "hidden",
        "submit",
        "button",
        "reset",
        "image",
    }
    _PROGRESS_LABELS = (
        "next",
        "continue",
        "save and continue",
        "review application",
        "continue to application",
    )
    _START_LABELS = (
        "apply",
        "apply now",
        "apply for this job",
        "apply to this job",
        "start application",
    )

    def __init__(self, driver: Any, *, timeout_seconds: float) -> None:
        self._driver = driver
        self._timeout_seconds = timeout_seconds
        self._targets: dict[str, _FieldTarget] = {}
        self._closed = False
        self._inspection_number = 0

    @property
    def current_url(self) -> str:
        return str(self._driver.current_url)

    def inspect_fields(self) -> tuple[ApplicationFormField, ...]:
        self._ensure_open()
        self._targets = {}
        self._inspection_number += 1
        field_prefix = f"step-{self._inspection_number}-field"
        counter = 0
        for frame_path in self._frame_paths():
            self._switch_to(frame_path)
            elements = self._driver.find_elements(
                "css selector",
                "input, textarea, select",
            )
            radios: dict[str, list[Any]] = {}
            for element in elements:
                tag = str(element.tag_name).casefold()
                input_type = (
                    str(element.get_attribute("type") or "text").casefold()
                    if tag == "input"
                    else ""
                )
                if input_type == "file":
                    try:
                        if not element.is_enabled():
                            continue
                    except Exception:
                        continue
                elif not self._is_interactable(element):
                    continue
                if tag == "input" and input_type in self._IGNORED_INPUT_TYPES:
                    continue
                if tag == "input" and input_type == "radio":
                    group = str(
                        element.get_attribute("name")
                        or element.get_attribute("id")
                        or f"radio-{counter}"
                    )
                    radios.setdefault(group, []).append(element)
                    continue
                counter += 1
                field_id = f"{field_prefix}-{counter:03d}"
                field = self._describe_element(field_id, element, tag, input_type)
                if field is None:
                    continue
                self._targets[field_id] = _FieldTarget(
                    field=field,
                    frame_path=frame_path,
                    elements=(element,),
                )
            for elements_in_group in radios.values():
                counter += 1
                field_id = f"{field_prefix}-{counter:03d}"
                labels = tuple(self._label(element) for element in elements_in_group)
                labels = tuple(
                    label or str(element.get_attribute("value") or "")
                    for label, element in zip(labels, elements_in_group)
                )
                labels = tuple(label for label in labels if label)
                if not labels or len(labels) != len(elements_in_group):
                    continue
                group_label = self._group_label(elements_in_group[0])
                field = ApplicationFormField(
                    field_id=field_id,
                    label=group_label or " / ".join(labels),
                    kind=ApplicationFieldKind.RADIO,
                    required=any(self._required(element) for element in elements_in_group),
                    options=labels,
                    current_value=next(
                        (
                            label
                            for label, element in zip(labels, elements_in_group)
                            if element.is_selected()
                        ),
                        "",
                    ),
                )
                self._targets[field_id] = _FieldTarget(
                    field=field,
                    frame_path=frame_path,
                    elements=tuple(elements_in_group),
                    option_labels=labels,
                )
        self._driver.switch_to.default_content()
        return tuple(target.field for target in self._targets.values())

    def fill_fields(
        self,
        answers: Mapping[str, str],
        *,
        resume_path: Path,
    ) -> ApplicationFillResult:
        self._ensure_open()
        resolved_resume = resume_path.resolve()
        if not resolved_resume.is_file():
            raise FileNotFoundError(f"generated resume not found: {resolved_resume}")
        filled: list[str] = []
        unresolved: list[ApplicationFormField] = []
        failures: list[str] = []
        resume_uploaded = False
        ordered_targets = sorted(
            self._targets.items(),
            key=lambda item: item[1].field.kind is ApplicationFieldKind.FILE,
        )
        for field_id, target in ordered_targets:
            field = target.field
            if field.current_value:
                continue
            if field.kind is ApplicationFieldKind.FILE:
                if self._is_resume_field(field):
                    try:
                        self._switch_to(target.frame_path)
                        upload = target.elements[0]
                        if not upload.is_displayed():
                            self._driver.execute_script(
                                """
                                arguments[0].style.display = 'block';
                                arguments[0].style.visibility = 'visible';
                                arguments[0].style.opacity = '1';
                                """,
                                upload,
                            )
                        upload.send_keys(str(resolved_resume))
                    except Exception as error:
                        failures.append(
                            f"{field.label}: {type(error).__name__}: {error}"
                        )
                        if field.required:
                            unresolved.append(field)
                    else:
                        filled.append(field_id)
                        resume_uploaded = True
                elif field.required:
                    unresolved.append(field)
                continue
            answer = answers.get(field_id)
            if answer is None:
                if field.required:
                    unresolved.append(field)
                continue
            try:
                self._fill_target(target, answer)
            except Exception as error:
                failures.append(f"{field.label}: {type(error).__name__}: {error}")
                if field.required:
                    unresolved.append(field)
            else:
                filled.append(field_id)
        self._driver.switch_to.default_content()
        unresolved_unique = tuple(
            {field.field_id: field for field in unresolved}.values()
        )
        return ApplicationFillResult(
            filled_field_ids=tuple(filled),
            unresolved_required_fields=unresolved_unique,
            failures=tuple(failures),
            resume_uploaded=resume_uploaded,
        )

    def open_application_form(self) -> bool:
        self._ensure_open()
        for frame_path in self._frame_paths():
            self._switch_to(frame_path)
            controls = self._driver.find_elements(
                "css selector",
                "a, button, input[type='button']",
            )
            for control in controls:
                if not self._is_interactable(control):
                    continue
                label = self._control_label(control)
                if label not in self._START_LABELS:
                    continue
                try:
                    inside_form = bool(
                        self._driver.execute_script(
                            "return Boolean(arguments[0].closest('form'));",
                            control,
                        )
                    )
                except Exception:
                    inside_form = True
                if inside_form:
                    continue
                control.click()
                self._wait_after_navigation()
                self._driver.switch_to.default_content()
                return True
        self._driver.switch_to.default_content()
        return False

    def advance(self) -> bool:
        self._ensure_open()
        for frame_path in self._frame_paths():
            self._switch_to(frame_path)
            controls = self._driver.find_elements(
                "css selector",
                "button, input[type='button'], input[type='submit'], a",
            )
            for control in controls:
                if not self._is_interactable(control):
                    continue
                label = self._control_label(control)
                if not self._is_progress_label(label):
                    continue
                control.click()
                self._wait_after_navigation()
                self._driver.switch_to.default_content()
                return True
        self._driver.switch_to.default_content()
        return False

    def disable_submission(self) -> int:
        self._ensure_open()
        disabled = 0
        script = """
            const controls = Array.from(document.querySelectorAll(
                "form button, form input[type='submit'], form input[type='image']"
            ));
            let count = 0;
            for (const control of controls) {
                const label = String(
                    control.innerText || control.value ||
                    control.getAttribute('aria-label') || ''
                ).trim().toLowerCase().replace(/\\s+/g, ' ');
                const progress = label.startsWith('next') ||
                    label.startsWith('continue') ||
                    label.startsWith('save and continue') ||
                    label.startsWith('review application');
                const finalAction = label.includes('submit') ||
                    label.includes('send application') ||
                    label.includes('complete application') ||
                    label.includes('finish application');
                const type = String(
                    control.getAttribute('type') ||
                    (control.tagName === 'BUTTON' ? 'submit' : '')
                ).toLowerCase();
                const implicitFinalSubmit = type === 'submit' && !progress;
                if (!progress && (finalAction || implicitFinalSubmit)) {
                    const alreadyDisabled =
                        control.getAttribute('data-job-agent-submit-disabled') === 'true';
                    control.disabled = true;
                    control.setAttribute('aria-disabled', 'true');
                    control.setAttribute('data-job-agent-submit-disabled', 'true');
                    if (!alreadyDisabled) count += 1;
                }
            }
            return count;
        """
        for frame_path in self._frame_paths():
            self._switch_to(frame_path)
            try:
                disabled += int(self._driver.execute_script(script) or 0)
            except Exception:
                continue
        self._driver.switch_to.default_content()
        return disabled

    def close(self) -> None:
        if not self._closed:
            self._driver.quit()
            self._closed = True

    def _describe_element(
        self,
        field_id: str,
        element: Any,
        tag: str,
        input_type: str,
    ) -> ApplicationFormField | None:
        label = self._label(element)
        if not label:
            return None
        if tag == "textarea":
            kind = ApplicationFieldKind.TEXTAREA
            options: tuple[str, ...] = ()
        elif tag == "select":
            kind = ApplicationFieldKind.SELECT
            options = tuple(
                option.text.strip()
                for option in element.find_elements("tag name", "option")
                if option.text.strip()
                and str(option.get_attribute("value") or "").strip()
            )
            if not options:
                return None
        elif input_type == "checkbox":
            kind = ApplicationFieldKind.CHECKBOX
            options = ()
        elif input_type == "file":
            kind = ApplicationFieldKind.FILE
            options = ()
        else:
            kind = ApplicationFieldKind.TEXT
            options = ()
        current = ""
        if kind is ApplicationFieldKind.CHECKBOX:
            current = "true" if element.is_selected() else ""
        elif kind is not ApplicationFieldKind.FILE:
            current = str(element.get_attribute("value") or "").strip()
        return ApplicationFormField(
            field_id=field_id,
            label=label,
            kind=kind,
            required=self._required(element),
            options=options,
            current_value=current,
        )

    def _fill_target(self, target: _FieldTarget, answer: str) -> None:
        self._switch_to(target.frame_path)
        field = target.field
        element = target.elements[0]
        if field.kind is ApplicationFieldKind.SELECT:
            try:
                from selenium.webdriver.support.ui import Select
            except ImportError as error:
                raise ApplicationBrowserDependencyError(
                    "install Selenium support with: pip install -e '.[browser]'"
                ) from error
            Select(element).select_by_visible_text(answer)
        elif field.kind is ApplicationFieldKind.RADIO:
            normalized = normalize_text(answer)
            for label, option in zip(target.option_labels, target.elements):
                if normalize_text(label) == normalized:
                    if not option.is_selected():
                        option.click()
                    return
            raise ValueError(f"unsupported radio option: {answer}")
        elif field.kind is ApplicationFieldKind.CHECKBOX:
            desired = answer.casefold() == "true"
            if bool(element.is_selected()) != desired:
                element.click()
        else:
            element.clear()
            element.send_keys(answer.replace("\r", " ").replace("\n", " "))

    def _frame_paths(self) -> tuple[tuple[int, ...], ...]:
        paths: list[tuple[int, ...]] = [()]
        index = 0
        while index < len(paths):
            path = paths[index]
            index += 1
            if len(path) >= 2:
                continue
            try:
                self._switch_to(path)
                frames = self._driver.find_elements("css selector", "iframe, frame")
            except Exception:
                continue
            paths.extend(path + (frame_index,) for frame_index in range(len(frames)))
        self._driver.switch_to.default_content()
        return tuple(paths)

    def _switch_to(self, frame_path: tuple[int, ...]) -> None:
        self._driver.switch_to.default_content()
        for frame_index in frame_path:
            frames = self._driver.find_elements("css selector", "iframe, frame")
            self._driver.switch_to.frame(frames[frame_index])

    def _label(self, element: Any) -> str:
        try:
            label = self._driver.execute_script(
                """
                const element = arguments[0];
                const labels = element.labels ? Array.from(element.labels) : [];
                const explicit = labels.map(value => value.innerText).join(' ').trim();
                if (explicit) return explicit;
                const wrapping = element.closest('label');
                if (wrapping && wrapping.innerText.trim()) return wrapping.innerText.trim();
                return element.getAttribute('aria-label') ||
                    element.getAttribute('placeholder') ||
                    element.getAttribute('name') ||
                    element.getAttribute('id') || '';
                """,
                element,
            )
        except Exception:
            label = None
        if not isinstance(label, str) or not label.strip():
            label = (
                element.get_attribute("aria-label")
                or element.get_attribute("placeholder")
                or element.get_attribute("name")
                or element.get_attribute("id")
                or ""
            )
        return " ".join(str(label).split())

    def _group_label(self, element: Any) -> str:
        try:
            value = self._driver.execute_script(
                """
                const fieldset = arguments[0].closest('fieldset');
                const legend = fieldset ? fieldset.querySelector('legend') : null;
                return legend ? legend.innerText.trim() : '';
                """,
                element,
            )
        except Exception:
            return ""
        return " ".join(value.split()) if isinstance(value, str) else ""

    @staticmethod
    def _required(element: Any) -> bool:
        return element.get_attribute("required") is not None or str(
            element.get_attribute("aria-required") or ""
        ).casefold() == "true"

    @staticmethod
    def _is_interactable(element: Any) -> bool:
        try:
            return bool(element.is_displayed() and element.is_enabled())
        except Exception:
            return False

    @staticmethod
    def _is_resume_field(field: ApplicationFormField) -> bool:
        label = normalize_text(field.label)
        return "resume" in label or "cv" in label or "curriculum vitae" in label

    @staticmethod
    def _control_label(control: Any) -> str:
        return normalize_text(
            str(
                control.text
                or control.get_attribute("value")
                or control.get_attribute("aria-label")
                or ""
            )
        )

    def _is_progress_label(self, label: str) -> bool:
        return any(label.startswith(value) for value in self._PROGRESS_LABELS)

    def _wait_after_navigation(self) -> None:
        time.sleep(min(1.0, max(0.1, self._timeout_seconds / 30)))

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("application browser session is closed")
