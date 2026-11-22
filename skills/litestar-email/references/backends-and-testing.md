# Litestar Email — Backends, SES, Exceptions, and Testing

## Pick a Backend

| Existing project constraint | Configuration | Extra |
| --- | --- | --- |
| Local output only | `backend="console"` | None |
| Unit or integration tests | `backend="memory"` | None |
| SMTP server or Mailpit | `backend=SMTPConfig(...)` | `smtp` |
| Existing Resend account | `backend=ResendConfig(...)` | `httpx` or `aiohttp` |
| Existing SendGrid account | `backend=SendGridConfig(...)` | `httpx` or `aiohttp` |
| Existing Mailgun account | `backend=MailgunConfig(...)` | `httpx` or `aiohttp` |
| Existing AWS SES setup | `backend=SESConfig(...)` | `ses` plus `httpx` or `aiohttp` |
| Project-owned backend | Registered name or backend-class import path | Project-specific |

Backend config fields:

| Config | Fields and defaults |
| --- | --- |
| `SMTPConfig` | `host="localhost"`, `port=25`, `username=None`, `password=None`, `use_tls=False`, `use_ssl=False`, `timeout=30` |
| `ResendConfig` | `api_key=""`, `timeout=30`, `http_transport="httpx"` |
| `SendGridConfig` | `api_key=""`, `timeout=30`, `http_transport="httpx"` |
| `MailgunConfig` | `api_key=""`, `domain=""`, `region="us"`, `timeout=30`, `http_transport="httpx"` |
| `SESConfig` | `region="us-east-1"`, `aws_access_key_id=None`, `aws_secret_access_key=None`, `aws_session_token=None`, `timeout=30`, `http_transport="httpx"` |

For SMTP, `use_tls=True` performs STARTTLS after connecting; `use_ssl=True`
uses implicit TLS. Select the mode required by the SMTP server.

For HTTP backends, `http_transport` accepts `"httpx"`, `"aiohttp"`, or an
`HTTPTransport` class (`from litestar_email.transports import HTTPTransport, HTTPResponse, get_transport`). Keep the default when the project has no transport preference.

For custom backends, subclass `BaseEmailBackend` and either pass its dotted
import path to `EmailConfig(backend="my_app.email.CustomBackend")` or register a
short name with `@email_backend("custom")`. Inspect registered names with
`list_backends()` and resolve classes or instances with `get_backend_class()` or
`get_backend()`. `ConsoleBackend` also accepts `stream: TextIO | None = None`
when instantiated directly.

## Amazon SES Contract

The 0.4.0 SES backend:

- calls the SES API v2 `SendEmail` endpoint with `Simple` content;
- signs the exact transmitted JSON bytes with botocore SigV4;
- uses explicit `SESConfig` credentials when both `aws_access_key_id` and
  `aws_secret_access_key` are set (with optional `aws_session_token`);
- otherwise uses botocore's default credential chain;
- supports text plus the first `text/html` alternative;
- supports `to`, `cc`, `bcc`, and the complete `reply_to` list;
- rejects attachments with `EmailDeliveryError` because `Simple` content does
  not support raw MIME attachments;
- rejects messages with neither a non-empty text body nor an HTML alternative;
- always propagates `EmailRateLimitError` and `EmailAuthenticationError`, even
  when `fail_silently=True` (all HTTP API backends -- Resend, SendGrid, Mailgun,
  and SES -- always propagate `EmailRateLimitError`).

Use SMTP or another attachment-capable backend when the message includes
files. Do not imply that SES 0.4.0 sends raw MIME content.

## Service Lifecycle

```python
from litestar_email import EmailConfig, EmailMessage, SMTPConfig

config = EmailConfig(
    backend=SMTPConfig(host="localhost", port=1025),
    from_email="noreply@example.com",
)

messages = [
    EmailMessage(subject="One", body="First", to=["one@example.com"]),
    EmailMessage(subject="Two", body="Second", to=["two@example.com"]),
]

async with config.provide_service() as mailer:
    sent = await mailer.send_messages(messages)
```

Outside a service context, each `send_message()` or `send_messages()` call
creates, opens, and closes a backend. Inside `config.provide_service()` or
`async with EmailService(config)`, calls reuse one open backend until context
exit. When bound via `Provide(config.provide_service().__aiter__)` (or a Dishka
request-scoped async generator), DI enters and closes that context per request.

`send_messages([])` returns `0`. `send_message(message)` delegates to
`send_messages([message])` and returns `0` or `1`.

## Exception Hierarchy

```text
EmailError
├── EmailBackendError
├── EmailDeliveryError
│   ├── EmailConnectionError
│   ├── EmailAuthenticationError
│   └── EmailRateLimitError
└── MissingDependencyError (also inherits ImportError)
```

`EmailRateLimitError.retry_after` is `int | None`. Unknown backend names raise
`ValueError`; missing optional packages raise `MissingDependencyError`.
Catch specific delivery failures before `EmailDeliveryError`:

```python
from litestar_email import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailDeliveryError,
    EmailRateLimitError,
)

try:
    await mailer.send_message(message)
except EmailRateLimitError as exc:
    await schedule_retry(delay=exc.retry_after or 60)
except EmailAuthenticationError:
    await alert_operators("Email credentials were rejected")
except EmailConnectionError:
    await schedule_retry(delay=30)
except EmailDeliveryError:
    await record_delivery_failure()
```

## In-Memory Testing

`InMemoryBackend.outbox` is a class-level list shared by every memory backend
instance. Clear it around each test:

```python
from collections.abc import Iterator

import pytest
from litestar_email import EmailConfig, EmailMessage
from litestar_email.backends import InMemoryBackend


@pytest.fixture(autouse=True)
def clear_email_outbox() -> Iterator[None]:
    InMemoryBackend.clear()
    yield
    InMemoryBackend.clear()


@pytest.mark.anyio
async def test_welcome_email() -> None:
    config = EmailConfig(backend="memory", from_email="test@example.com")

    async with config.provide_service() as mailer:
        sent = await mailer.send_message(
            EmailMessage(
                subject="Welcome",
                body="Thanks for signing up.",
                to=["user@example.com"],
            ),
        )

    assert sent == 1
    assert len(InMemoryBackend.outbox) == 1
    assert InMemoryBackend.outbox[0].subject == "Welcome"
```

For direct backend tests, use `backend = config.get_backend()` and await
`backend.send_messages([...])`. In-memory inspection uses `InMemoryBackend.outbox`.
