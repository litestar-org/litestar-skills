"""Upstream contract verification for litestar-email 0.4.0."""

import dataclasses
import inspect
import io
from importlib.metadata import version

import pytest
from litestar import Litestar
from litestar_email import (
    AsyncServiceProvider,
    BaseEmailBackend,
    ConsoleBackend,
    EmailAuthenticationError,
    EmailBackendError,
    EmailConfig,
    EmailConnectionError,
    EmailDeliveryError,
    EmailError,
    EmailMessage,
    EmailMultiAlternatives,
    EmailPlugin,
    EmailRateLimitError,
    EmailService,
    InMemoryBackend,
    MailgunBackend,
    MailgunConfig,
    MissingDependencyError,
    ResendBackend,
    ResendConfig,
    SendGridBackend,
    SendGridConfig,
    SESBackend,
    SESConfig,
    SMTPBackend,
    SMTPConfig,
    email_backend,
    get_backend,
    get_backend_class,
    list_backends,
)
from litestar_email.transports import HTTPResponse, HTTPTransport, get_transport


def test_litestar_email_040_version_and_exports() -> None:
    """Verify installed version and public symbol exports for litestar-email 0.4.0."""
    assert version("litestar-email") == "0.4.0"
    assert set(list_backends()) >= {
        "console",
        "memory",
        "smtp",
        "resend",
        "ses",
        "sendgrid",
        "mailgun",
    }
    assert get_backend_class("console") is ConsoleBackend
    assert get_backend_class("memory") is InMemoryBackend
    assert get_backend_class("smtp") is SMTPBackend
    assert get_backend_class("resend") is ResendBackend
    assert get_backend_class("sendgrid") is SendGridBackend
    assert get_backend_class("mailgun") is MailgunBackend
    assert get_backend_class("ses") is SESBackend
    assert all(
        symbol is not None
        for symbol in (
            AsyncServiceProvider,
            BaseEmailBackend,
            HTTPResponse,
            HTTPTransport,
            email_backend,
            get_backend,
            get_transport,
        )
    )


def test_litestar_email_040_backend_configs_and_email_config_defaults() -> None:
    """Verify exact fields and defaults of EmailConfig and all backend config dataclasses."""
    email_cfg = EmailConfig()
    assert email_cfg.backend == "console"
    assert email_cfg.from_email == "noreply@localhost"
    assert email_cfg.from_name == ""
    assert email_cfg.fail_silently is False
    assert (email_cfg.email_service_dependency_key, email_cfg.email_service_state_key) == (
        "mailer",
        "mailer",
    )
    assert isinstance(email_cfg.provide_service(), AsyncServiceProvider)
    assert "EmailService" in email_cfg.signature_namespace

    smtp_cfg = SMTPConfig()
    assert (
        smtp_cfg.host,
        smtp_cfg.port,
        smtp_cfg.username,
        smtp_cfg.password,
        smtp_cfg.use_tls,
        smtp_cfg.use_ssl,
        smtp_cfg.timeout,
    ) == ("localhost", 25, None, None, False, False, 30)

    resend_cfg = ResendConfig()
    assert (resend_cfg.api_key, resend_cfg.timeout, resend_cfg.http_transport) == (
        "",
        30,
        "httpx",
    )

    sendgrid_cfg = SendGridConfig()
    assert (sendgrid_cfg.api_key, sendgrid_cfg.timeout, sendgrid_cfg.http_transport) == (
        "",
        30,
        "httpx",
    )

    mailgun_cfg = MailgunConfig()
    assert (
        mailgun_cfg.api_key,
        mailgun_cfg.domain,
        mailgun_cfg.region,
        mailgun_cfg.timeout,
        mailgun_cfg.http_transport,
    ) == ("", "", "us", 30, "httpx")

    ses_cfg = SESConfig()
    assert {f.name for f in dataclasses.fields(SESConfig)} == {
        "region",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "timeout",
        "http_transport",
    }
    assert (
        ses_cfg.region,
        ses_cfg.aws_access_key_id,
        ses_cfg.aws_secret_access_key,
        ses_cfg.aws_session_token,
        ses_cfg.timeout,
        ses_cfg.http_transport,
    ) == ("us-east-1", None, None, None, 30, "httpx")


def test_litestar_email_040_message_and_multi_alternatives_contract() -> None:
    """Verify EmailMessage and EmailMultiAlternatives constructor signatures and methods."""
    assert list(inspect.signature(EmailMessage).parameters) == [
        "subject",
        "body",
        "from_email",
        "to",
        "cc",
        "bcc",
        "reply_to",
        "headers",
        "attachments",
        "alternatives",
    ]
    assert "html_body" not in inspect.signature(EmailMessage).parameters
    assert "html_body" in inspect.signature(EmailMultiAlternatives).parameters

    msg = EmailMultiAlternatives(
        subject="Report",
        body="Plain text",
        to=["to@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
        html_body="<p>HTML</p>",
    )
    msg.attach("report.pdf", b"bytes", "application/pdf")
    assert msg.recipients() == ["to@example.com", "cc@example.com", "bcc@example.com"]
    assert msg.alternatives == [("<p>HTML</p>", "text/html")]
    assert msg.attachments == [("report.pdf", b"bytes", "application/pdf")]


@pytest.mark.anyio
async def test_litestar_email_040_plugin_service_and_backends_contract() -> None:
    """Verify EmailPlugin registration, EmailService lifecycle, InMemoryBackend, and ConsoleBackend."""
    InMemoryBackend.clear()
    config = EmailConfig(
        backend="memory",
        from_email="noreply@example.com",
        from_name="Example",
        email_service_dependency_key="email_service",
        email_service_state_key="email_config",
    )
    plugin = EmailPlugin(config=config)
    app = Litestar(route_handlers=[], plugins=[plugin])

    assert "email_service" in app.dependencies
    assert app.state["email_config"] is config
    assert isinstance(plugin.get_service(app.state), EmailService)

    async with config.provide_service() as mailer:
        assert await mailer.send_messages([]) == 0
        sent = await mailer.send_message(
            EmailMessage(subject="Hello", body="World", to=["user@example.com"]),
        )
        assert sent == 1

    assert len(InMemoryBackend.outbox) == 1
    assert InMemoryBackend.outbox[0].subject == "Hello"
    InMemoryBackend.clear()
    assert InMemoryBackend.outbox == []

    stream = io.StringIO()
    console_backend = ConsoleBackend(
        stream=stream,
        default_from_email="noreply@example.com",
        default_from_name="Example",
    )
    written = await console_backend.send_messages(
        [EmailMessage(subject="Console", body="Body", to=["dev@example.com"])]
    )
    assert written == 1
    assert "Subject: Console" in stream.getvalue()


def test_litestar_email_040_exception_hierarchy_contract() -> None:
    """Verify exception inheritance and EmailRateLimitError retry_after attribute."""
    assert issubclass(EmailBackendError, EmailError)
    assert issubclass(EmailDeliveryError, EmailError)
    assert issubclass(EmailConnectionError, EmailDeliveryError)
    assert issubclass(EmailAuthenticationError, EmailDeliveryError)
    assert issubclass(EmailRateLimitError, EmailDeliveryError)
    assert issubclass(MissingDependencyError, (EmailError, ImportError))

    rate_err = EmailRateLimitError("Rate limited", retry_after=45)
    assert rate_err.retry_after == 45
    assert EmailRateLimitError("Rate limited").retry_after is None

    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend_class("nonexistent_backend")
    with pytest.raises(ValueError, match="Unknown transport"):
        get_transport("nonexistent_transport")
