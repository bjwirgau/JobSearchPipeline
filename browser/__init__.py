"""Review-first browser automation planning; no live browser runs in Phase 1."""

from .browser_manager import BrowserManager, BrowserSession
from .form_filler import FormFillPlan, FormFiller
from .question_handler import QuestionHandler
from .page_loader import BrowserDependencyError, PlaywrightPageLoader, SeleniumPageLoader

__all__ = [
    "BrowserDependencyError",
    "BrowserManager",
    "BrowserSession",
    "FormFillPlan",
    "FormFiller",
    "PlaywrightPageLoader",
    "QuestionHandler",
    "SeleniumPageLoader",
]
