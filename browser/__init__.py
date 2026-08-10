"""Review-first browser automation planning; no live browser runs in Phase 1."""

from .browser_manager import BrowserManager, BrowserSession
from .form_filler import FormFillPlan, FormFiller
from .question_handler import QuestionHandler
from .page_loader import BrowserDependencyError, PlaywrightPageLoader, SeleniumPageLoader
from .selenium_application import (
    ApplicationBrowser,
    ApplicationBrowserDependencyError,
    ApplicationBrowserDisabledError,
    ApplicationBrowserNavigationError,
    ApplicationBrowserSession,
    SeleniumApplicationBrowser,
    SeleniumApplicationSession,
)

__all__ = [
    "BrowserDependencyError",
    "ApplicationBrowser",
    "ApplicationBrowserDependencyError",
    "ApplicationBrowserDisabledError",
    "ApplicationBrowserNavigationError",
    "ApplicationBrowserSession",
    "BrowserManager",
    "BrowserSession",
    "FormFillPlan",
    "FormFiller",
    "PlaywrightPageLoader",
    "QuestionHandler",
    "SeleniumPageLoader",
    "SeleniumApplicationBrowser",
    "SeleniumApplicationSession",
]
