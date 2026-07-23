import inspect
from importlib.metadata import version

from litestar_email import EmailConfig, EmailMessage, EmailMultiAlternatives
from litestar_email.backends.memory import InMemoryBackend
from litestar_email.exceptions import MissingDependencyError


def test_litestar_email_040_message_state_and_memory_contract() -> None:
    assert version("litestar-email") == "0.4.0"
    assert list(inspect.signature(EmailMessage).parameters)[:3] == [
        "subject",
        "body",
        "from_email",
    ]
    assert "html_body" in inspect.signature(EmailMultiAlternatives).parameters
    config = EmailConfig()
    assert (config.email_service_dependency_key, config.email_service_state_key) == (
        "mailer",
        "mailer",
    )
    assert InMemoryBackend.outbox == []
    assert issubclass(MissingDependencyError, ImportError)
