---
name: litestar-email
description: "Use when working with litestar_email, EmailPlugin, EmailConfig, EmailService, EmailMessage, EmailMultiAlternatives, InMemoryBackend, SMTPConfig, ResendConfig, SendGridConfig, MailgunConfig, SESConfig. Not for marketing APIs — use vendor SDKs."
---

# litestar-email

`litestar-email` 0.4.0 provides one async sending interface for console, memory,
SMTP, Resend, SendGrid, Mailgun, Amazon SES, and custom backends. Match the
backend already selected by the project; keep message construction independent
from the transport.

## Code Style Rules

- Use `NamedDependency[EmailService]` with `Provide(email_config.provide_service().__aiter__)`
  (or `FromDishka[EmailService]` when the project uses Dishka) for direct
  `EmailService` handler injection.
- Pass recipient collections as `list[str]`. `to`, `cc`, `bcc`, and `reply_to`
  are list fields.
- Pass attachment content as `bytes`. Do file I/O before constructing the
  message and keep that I/O async.
- Await `send_message()` and `send_messages()`. Both return the count sent.
- Keep API keys and SMTP credentials in the project's settings layer.

## Quick Reference

### Install

```bash
pip install "litestar-email>=0.4.0"
pip install "litestar-email[smtp]>=0.4.0"   # aiosmtplib
pip install "litestar-email[ses]>=0.4.0"    # botocore for SigV4
pip install "litestar-email[httpx]>=0.4.0"   # default HTTP transport
pip install "litestar-email[aiohttp]>=0.4.0" # alternative HTTP transport
```

The HTTP API backends select `httpx` by default, but the transport is optional
in `litestar-email` itself. Install the `httpx` or `aiohttp` extra (unless the
project already provides that dependency), and select `aiohttp` only when the
project standardizes on it.

### Configure the Plugin

```python
from os import environ

from litestar import Litestar
from litestar_email import EmailConfig, EmailPlugin, SMTPConfig

email_config = EmailConfig(
    backend=SMTPConfig(
        host="smtp.example.com",
        port=587,
        username=environ["SMTP_USERNAME"],
        password=environ["SMTP_PASSWORD"],
        use_tls=True,
    ),
    from_email="noreply@example.com",
    from_name="Example App",
)

app = Litestar(plugins=[EmailPlugin(config=email_config)])
```

`EmailConfig` fields:

| Field | Default | Contract |
| --- | --- | --- |
| `backend` | `"console"` | Registered name, import path, or built-in backend config object |
| `from_email` | `"noreply@localhost"` | Default sender address |
| `from_name` | `""` | Default display name |
| `fail_silently` | `False` | Backend-specific best-effort delivery behavior |
| `email_service_dependency_key` | `"mailer"` | Litestar DI key |
| `email_service_state_key` | `"mailer"` | Key holding the config in app state |

The dependency and state keys occupy separate namespaces. Change them
independently when the application already uses either key:

```python
email_config = EmailConfig(
    backend="memory",
    email_service_dependency_key="email_service",
    email_service_state_key="email_config",
)
```

### Inject `EmailService`

`EmailPlugin.on_app_init()` registers:

- `Provide(config.provide_service, sync_to_thread=False)` under `email_service_dependency_key`;
- `config.signature_namespace` (`BaseEmailBackend`, `EmailConfig`, `EmailMessage`,
  `EmailMultiAlternatives`, `EmailService`, `MailgunConfig`, `ResendConfig`,
  `SESConfig`, `SMTPConfig`, `SendGridConfig`) in Litestar's signature namespace;
- the `EmailConfig` instance under `email_service_state_key` in app state.

Because `EmailConfig.provide_service()` is a synchronous method returning an
`AsyncServiceProvider` instance rather than an `async def` generator function,
Litestar's default `Provide(config.provide_service, sync_to_thread=False)`
injects `AsyncServiceProvider` rather than `EmailService`.

To inject an open `EmailService` with request-scoped connection cleanup, bind
`Provide(email_config.provide_service().__aiter__)` on the router, controller,
or handler (or use Dishka's `FromDishka[EmailService]`):

```python
from litestar import post
from litestar.di import NamedDependency, Provide
from litestar_email import EmailConfig, EmailMessage, EmailService

email_config = EmailConfig(backend="memory", from_email="noreply@example.com")


@post(
    "/notifications",
    dependencies={"mailer": Provide(email_config.provide_service().__aiter__)},
)
async def send_notification(
    mailer: NamedDependency[EmailService],
) -> dict[str, int]:
    sent = await mailer.send_message(
        EmailMessage(
            subject="Notification",
            body="You have a new notification.",
            to=["recipient@example.com"],
        ),
    )
    return {"sent": sent}
```

If using the plugin's default dependency directly without overriding
`dependencies`, register `signature_types=[AsyncServiceProvider]`, annotate the
parameter as `mailer: NamedDependency[AsyncServiceProvider]`, and enter
`async with mailer as service:` inside the handler.

If the project uses Dishka, yield `EmailService` from a `Scope.REQUEST` provider
and inject `FromDishka[EmailService]`:

```python
from collections.abc import AsyncIterator

from dishka import Provider, Scope
from dishka.integrations.litestar import FromDishka, inject
from litestar import post
from litestar_email import EmailConfig, EmailMessage, EmailService


def build_email_provider(config: EmailConfig) -> Provider:
    async def provide_mailer() -> AsyncIterator[EmailService]:
        async with config.provide_service() as mailer:
            yield mailer

    provider = Provider(scope=Scope.REQUEST)
    provider.provide(provide_mailer)
    return provider


@post("/welcome")
@inject
async def send_welcome(
    email_service: FromDishka[EmailService],
) -> dict[str, int]:
    sent = await email_service.send_message(
        EmailMessage(subject="Welcome", body="Hello!", to=["user@example.com"]),
    )
    return {"sent": sent}
```

App state does not contain a permanently open `EmailService`. Use
`plugin.get_service(app.state)` or `config.get_service(app.state)` when code
outside handler DI needs a service derived from app state.

### Construct Messages

`subject` and `body` are required constructor arguments. Recipient lists have
empty-list defaults, so provide at least one delivery recipient before sending.

```python
from litestar_email import EmailMessage

message = EmailMessage(
    subject="Monthly report",
    body="The report is attached.",
    from_email="Reports <reports@example.com>",
    to=["owner@example.com"],
    cc=["audit@example.com"],
    bcc=["archive@example.com"],
    reply_to=["support@example.com"],
    headers={"X-Campaign-ID": "monthly-report"},
)
message.attach(
    filename="report.pdf",
    content=b"report content",
    mimetype="application/pdf",
)
message.attach_alternative(
    content="<p>The report is attached.</p>",
    mimetype="text/html",
)
```

`EmailMessage` does not accept `html_body` or `from_name`. Put a per-message
display name in `from_email`, as shown above. Use
`EmailMultiAlternatives.html_body` for the HTML convenience constructor:

```python
from litestar_email import EmailMultiAlternatives

message = EmailMultiAlternatives(
    subject="Welcome",
    body="Welcome to Example App.",
    to=["user@example.com"],
    html_body="<p>Welcome to <strong>Example App</strong>.</p>",
)
```

The message collections have these exact shapes:

| Field | Type |
| --- | --- |
| `to`, `cc`, `bcc`, `reply_to` | `list[str]` |
| `headers` | `dict[str, str]` |
| `attachments` | `list[tuple[str, bytes, str]]` |
| `alternatives` | `list[tuple[str, str]]` |

`recipients()` returns `to + cc + bcc`; it does not include `reply_to`.

### Backends, Lifecycle, Exceptions, and In-Memory Testing

| Backend / Use | Config | Extra |
| --- | --- | --- |
| Console / Tests | `backend="console"` or `backend="memory"` (`InMemoryBackend.outbox`) | None |
| SMTP | `backend=SMTPConfig(host=..., port=..., use_tls=...)` | `smtp` |
| Resend / SendGrid / Mailgun | `ResendConfig` / `SendGridConfig` / `MailgunConfig` | `httpx` or `aiohttp` |
| Amazon SES (`SendEmail` Simple) | `SESConfig(...)` (rejects MIME attachments with `EmailDeliveryError`) | `ses` + `httpx` or `aiohttp` |
| Custom | Subclass `BaseEmailBackend` or register with `@email_backend(...)` | Project-specific |

Inside `async with config.provide_service() as mailer:`, calls reuse one open backend; `Provide(config.provide_service().__aiter__)` scopes that lifecycle per request. Catch `EmailRateLimitError`, `EmailAuthenticationError`, and `EmailConnectionError` before `EmailDeliveryError`. Clear `InMemoryBackend.outbox` around tests. See [Backends, SES, Exceptions, and In-Memory Testing](references/backends-and-testing.md) for full config tables, SigV4 SES rules, `HTTPTransport`, exception hierarchy, and pytest fixtures.

<workflow>

## Workflow

1. Inspect the project's existing provider, network policy, and dependency
   extras. Keep its backend unless the user asks to migrate.
2. Build one `EmailConfig` with the selected backend config and default sender.
3. Register `EmailPlugin(config=...)` and wire handler DI with
   `Provide(email_config.provide_service().__aiter__)` +
   `NamedDependency[EmailService]` (or Dishka `FromDishka[EmailService]`).
4. Construct `EmailMessage` with plain text. Add HTML through
   `attach_alternative()` or `EmailMultiAlternatives`.
5. Load attachment bytes asynchronously, then call `attach()`.
6. Reuse a service context for batches. Let request-scoped DI manage service
   cleanup in handlers.
7. Use `backend="memory"` in tests and clear `InMemoryBackend.outbox` between
   tests.
8. For slow or retryable delivery, use the queue system already present in the
   project. Choose `litestar-queues` or `litestar-saq` only when it matches the
   existing stack.

</workflow>

<guardrails>

## Guardrails

- Do not pass `html_body` to `EmailMessage`; only
  `EmailMultiAlternatives` defines that field.
- Do not import nonexistent symbols such as `ConsoleConfig`, `InMemoryConfig`,
  `EmailAttachment`, `FallbackConfig`, `RateLimitConfig`, or `RetryConfig`.
  Console and memory backends use `backend="console"` and `backend="memory"`
  (no config dataclass); attachments are `(filename, content_bytes, mimetype)`
  tuples added via `attach()` or `attachments=[...]`.
- Do not pass file paths as attachments. Pass
  `(filename, content_bytes, mimetype)` or call `attach()`.
- Do not pass a string to `reply_to`; pass `list[str]`.
- Do not annotate a route handler with `mailer: NamedDependency[EmailService]`
  without binding `Provide(email_config.provide_service().__aiter__)` (or a
  Dishka provider); `EmailPlugin`'s default `Provide(config.provide_service, sync_to_thread=False)`
  returns `AsyncServiceProvider`.
- Do not read app state as an open service by default. The plugin stores its
  `EmailConfig` there and derives services from it.
- Do not configure a named API backend separately from its settings. Use
  `backend=ResendConfig(...)`, `backend=SendGridConfig(...)`,
  `backend=MailgunConfig(...)`, or `backend=SESConfig(...)`.
- Do not send SES attachments. Select an attachment-capable backend.
- Do not assume `fail_silently=True` suppresses every exception. Rate-limit
  failures (`EmailRateLimitError`) on HTTP API backends and SES authentication
  failures (`EmailAuthenticationError`) always propagate.
- Do not hard-code API keys, SMTP passwords, or AWS credentials.
- Do not force a provider migration. Match the project's deployed backend and
  operational constraints.

</guardrails>

<validation>

## Validation

- [ ] `litestar-email>=0.4.0` and the selected backend extra are installed.
- [ ] `EmailPlugin(config=...)` is registered.
- [ ] The handler name matches `email_service_dependency_key`.
- [ ] Handler injection binds `Provide(email_config.provide_service().__aiter__)` with `NamedDependency[EmailService]` (or uses Dishka `FromDishka[EmailService]`).
- [ ] `EmailMessage` supplies `subject`, `body`, and a delivery recipient.
- [ ] Attachments are byte triples and the selected backend supports them.
- [ ] HTML content is stored in `alternatives`, not passed to `EmailMessage`.
- [ ] SMTP TLS mode matches the server.
- [ ] SES messages contain no attachments and contain text or HTML.
- [ ] Batch sends reuse a managed service context.
- [ ] Tests clear and assert `InMemoryBackend.outbox`.
- [ ] Delivery exceptions are caught from most specific to least specific.
- [ ] Secrets come from the project's settings layer.

</validation>

<example>

## Example

```python
from dataclasses import dataclass
from html import escape

from litestar import Litestar, post
from litestar.di import NamedDependency, Provide
from litestar.params import JSONBody
from litestar_email import (
    EmailConfig,
    EmailMessage,
    EmailPlugin,
    EmailService,
)

email_config = EmailConfig(
    backend="memory",
    from_email="notifications@example.com",
    from_name="Example App",
)


@dataclass
class Notification:
    recipient: str
    subject: str
    text: str


@post(
    "/notifications",
    dependencies={"mailer": Provide(email_config.provide_service().__aiter__)},
)
async def create_notification(
    data: JSONBody[Notification],
    mailer: NamedDependency[EmailService],
) -> dict[str, int]:
    message = EmailMessage(
        subject=data.subject,
        body=data.text,
        to=[data.recipient],
    )
    message.attach_alternative(
        content=f"<p>{escape(data.text)}</p>",
        mimetype="text/html",
    )
    return {"sent": await mailer.send_message(message)}


app = Litestar(
    route_handlers=[create_notification],
    plugins=[EmailPlugin(config=email_config)],
)
```

</example>

## References Index

- **[Backends, SES, Lifecycle, Exceptions, and In-Memory Testing](references/backends-and-testing.md)** — SMTP / Resend / SendGrid / Mailgun / SES configs, custom backends, SigV4 rules, service context reuse, exception hierarchy, and `InMemoryBackend.outbox` fixtures.
- [Litestar dependency injection](../litestar/references/di-and-dishka.md)
- [Litestar settings](../litestar/references/settings.md)
- [Litestar Queues](../litestar-queues/SKILL.md)
- [Litestar SAQ](../litestar-saq/SKILL.md)
- [Litestar testing](../litestar-testing/SKILL.md)

## Official References

- [PyPI release 0.4.0](https://pypi.org/project/litestar-email/0.4.0/)
- [Message API at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/message.py)
- [Configuration API at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/config.py)
- [Plugin lifecycle at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/plugin.py)
- [Service lifecycle at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/service.py)
- [Exception hierarchy at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/exceptions.py)
- [SES backend at v0.4.0](https://github.com/litestar-org/litestar-email/blob/v0.4.0/src/litestar_email/backends/ses.py)
- [Tagged tests at v0.4.0](https://github.com/litestar-org/litestar-email/tree/v0.4.0/src/tests)

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
