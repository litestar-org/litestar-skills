---
name: litestar-email
description: "Auto-activate for litestar_email imports, EmailPlugin, EmailConfig, EmailService, EmailMessage, SMTPConfig, ResendConfig, SendGridConfig, MailgunConfig, or InMemoryConfig. Use when sending transactional email from Litestar, choosing an email backend, testing email flows, or injecting EmailService. Not for non-Litestar email SDK usage or marketing campaign platforms."
---

# litestar-email

`litestar-email` provides a pluggable email-sending abstraction for Litestar. One config + plugin, swap backends without touching call sites.

Backends:

- `SMTPConfig` — generic SMTP via `aiosmtplib`
- `ResendConfig` — Resend HTTP API
- `SendGridConfig` — SendGrid HTTP API
- `MailgunConfig` — Mailgun HTTP API
- `InMemoryConfig` — for tests; captures messages in an `outbox` list

## Code Style Rules

- PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations`
- Async all I/O — `EmailService.send_message` is `async`

## Quick Reference

### Install

```bash
pip install litestar-email
# Optional extras for specific backends:
pip install litestar-email[resend]
pip install litestar-email[sendgrid]
pip install litestar-email[mailgun]
```

### Basic Setup

```python
from litestar import Litestar
from litestar_email import EmailPlugin, EmailConfig, SMTPConfig

app = Litestar(plugins=[EmailPlugin(config=EmailConfig(
    backend=SMTPConfig(
        host="smtp.example.com",
        port=587,
        use_tls=True,
        username="user@example.com",
        password="secret",
    ),
    from_email="noreply@example.com",
    from_name="My App",
))])
```

### EmailConfig

| Option | Type | Description |
| --- | --- | --- |
| `backend` | `BackendConfig` | One of `SMTPConfig`, `ResendConfig`, `SendGridConfig`, `MailgunConfig`, `InMemoryConfig` |
| `from_email` | `str` | Default sender address |
| `from_name` | `str \| None` | Optional display name |

### Backend Configs

#### SMTPConfig

```python
from litestar_email import SMTPConfig

SMTPConfig(
    host="smtp.gmail.com",
    port=587,
    use_tls=True,           # STARTTLS
    use_ssl=False,          # Implicit SSL (port 465)
    username="you@gmail.com",
    password="app-password",
    timeout=10,
)
```

#### ResendConfig

```python
from litestar_email import ResendConfig
ResendConfig(api_key="re_xxxxxxxxxx")
```

#### SendGridConfig

```python
from litestar_email import SendGridConfig
SendGridConfig(api_key="SG.xxxxxxxxxx")
```

#### MailgunConfig

```python
from litestar_email import MailgunConfig
MailgunConfig(api_key="key-xxxxxxxxxx", domain="mg.example.com", region="us")
```

#### InMemoryConfig (testing)

```python
from litestar_email import InMemoryConfig
InMemoryConfig()
# Stores sent messages in memory; inspect via email_service.outbox
```

### Dependency Injection

`EmailPlugin.on_app_init` registers `EmailService` automatically.

```python
from litestar import post
from litestar_email import EmailService, EmailMessage

@post("/send-notification")
async def send_notification(
    email_service: EmailService,
    data: NotificationRequest,
) -> dict:
    await email_service.send_message(EmailMessage(
        to=[data.recipient],
        subject="Notification",
        body="You have a new notification.",
        html_body="<p>You have a new notification.</p>",
    ))
    return {"sent": True}
```

### EmailMessage

```python
from litestar_email import EmailMessage

EmailMessage(
    to=["recipient@example.com"],         # required
    subject="Hello",                       # required
    body="Plain text body",                # optional
    html_body="<p>HTML body</p>",          # optional
    cc=["cc@example.com"],
    bcc=["bcc@example.com"],
    reply_to="reply@example.com",
    from_email="override@example.com",     # overrides EmailConfig default
    from_name="Override Name",
    headers={"X-Custom": "value"},
    attachments=[("/path/to/file.pdf", "application/pdf")],
)
```

### EmailMultiAlternatives

```python
from litestar_email import EmailMultiAlternatives

msg = EmailMultiAlternatives(
    to=["user@example.com"],
    subject="Welcome",
    body="Welcome to our platform.",
)
msg.attach_alternative("<p>Welcome to our platform.</p>", "text/html")
await email_service.send_message(msg)
```

### EmailService Methods

| Method | Description |
| --- | --- |
| `send_message(msg)` | Send a single `EmailMessage` |
| `send_messages(msgs)` | Batch send |

Both are `async`.

### Connection Pooling (SMTP)

```python
async with email_service as svc:
    await svc.send_message(msg1)
    await svc.send_message(msg2)
```

### Standalone Usage (no DI)

```python
from litestar_email import EmailConfig, SMTPConfig, EmailMessage

config = EmailConfig(
    backend=SMTPConfig(host="smtp.example.com", port=587, use_tls=True),
    from_email="noreply@example.com",
)

async def main():
    async with config.provide_service() as email_service:
        await email_service.send_message(EmailMessage(
            to=["user@example.com"], subject="Hello", body="World",
        ))
```

### Templating

`litestar-email` does not ship a templating engine. Use Litestar's Jinja2 integration to render `body` / `html_body` strings before constructing `EmailMessage`:

```python
from litestar.template import TemplateEngineProtocol

async def send_welcome(
    email_service: EmailService,
    template_engine: TemplateEngineProtocol,
    user: User,
) -> None:
    html = template_engine.render("emails/welcome.html", {"user": user})
    text = template_engine.render("emails/welcome.txt", {"user": user})
    await email_service.send_message(EmailMessage(
        to=[user.email],
        subject="Welcome!",
        body=text,
        html_body=html,
    ))
```

<workflow>

## Workflow

### Step 1: Install + Pick Backend

| Need | Backend |
| --- | --- |
| Generic SMTP / corporate mail | `SMTPConfig` |
| Modern transactional API | `ResendConfig` (preferred for new projects) |
| Existing SendGrid contract | `SendGridConfig` |
| Mailgun account | `MailgunConfig` |
| Any test environment | `InMemoryConfig` |

### Step 2: Configure Plugin

Build `EmailConfig(backend=..., from_email=..., from_name=...)` and wrap in `EmailPlugin`. Add to `Litestar(plugins=[...])`.

### Step 3: Inject EmailService

In handlers / services, declare `email_service: EmailService` parameter. Litestar's DI provides it.

### Step 4: Construct EmailMessage

Use `EmailMessage` for simple sends. Use `EmailMultiAlternatives` if you need multiple HTML parts. Render templates separately if needed.

### Step 5: Background Send (recommended for slow ops)

For non-interactive flows, enqueue email sending via `litestar-saq` rather than blocking the request. See `../litestar-saq/SKILL.md`.

```python
await task_queues.get("default").enqueue(
    "send_welcome_email",
    user_id=user.id,
    timeout=30,
    retries=2,
    key=f"welcome-{user.id}",
)
```

### Step 6: Test with InMemoryConfig

In test config, swap `backend=InMemoryConfig()`. Assert against `email_service.outbox`.

</workflow>

<guardrails>

## Guardrails

- **Use `InMemoryConfig` in all test environments** — no real network calls; provides an `outbox` for assertions.
- **Background-queue email sends** — use `litestar-saq` for transactional email. SMTP can be slow; blocking handlers degrades p99.
- **Set `from_email` at the plugin level** — overriding per message is for exceptions, not the default.
- **Use `Resend` or `SendGrid` for high-volume transactional** — direct SMTP scales poorly past ~100/s.
- **Never log passwords/API keys** — sanitize `EmailConfig.backend` before structlog dumps.
- **Validate recipient addresses at the API boundary** — invalid addresses cause backend errors and waste retries.
- **Set timeouts** — `SMTPConfig.timeout` defaults are usually fine; tune if your SMTP host is slow.
- **Don't ship `[resend]` / `[sendgrid]` extras you don't use** — they pull in HTTP client deps.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering email-sending code, verify:

- [ ] `EmailPlugin` is in `app.plugins`
- [ ] Backend is appropriate for env (`InMemoryConfig` in tests, real backend in dev/prod)
- [ ] `from_email` is configured at the `EmailConfig` level
- [ ] Handler injects `EmailService` via DI (no module-level instance)
- [ ] `EmailMessage` is constructed with required `to` and `subject`
- [ ] Slow / retry-able sends are queued via `litestar-saq` instead of blocking the request
- [ ] Tests assert against `email_service.outbox`
- [ ] Secrets (`password`, `api_key`) come from env / settings, not hard-coded

</validation>

<example>

## Example

**Task:** Welcome-email flow that queues a SAQ task to send via Resend; test asserts via InMemoryConfig.

```python
# app/config/email.py
from litestar_email import EmailConfig, ResendConfig, InMemoryConfig
from app.lib.settings import get_settings

def get_email_config() -> EmailConfig:
    settings = get_settings()
    if settings.env == "test":
        return EmailConfig(backend=InMemoryConfig(), from_email="test@example.com")
    return EmailConfig(
        backend=ResendConfig(api_key=settings.resend.api_key),
        from_email=settings.email.from_email,
        from_name=settings.email.from_name,
    )
```

```python
# app/server/plugins.py
from litestar_email import EmailPlugin
from app.config.email import get_email_config

email = EmailPlugin(config=get_email_config())
```

```python
# app/domain/accounts/tasks.py
from litestar_email import EmailMessage

async def send_welcome_email(ctx: dict, *, user_id: int, email: str, name: str) -> None:
    """Send welcome email as a SAQ background task."""
    email_service = ctx["state"]["email_service"]
    template_engine = ctx["state"]["template_engine"]
    html = template_engine.render("emails/welcome.html", {"name": name})
    await email_service.send_message(EmailMessage(
        to=[email],
        subject=f"Welcome, {name}!",
        body=f"Welcome, {name}!",
        html_body=html,
    ))
```

```python
# app/domain/accounts/controllers.py
from litestar import Controller, post
from litestar_saq import TaskQueues

class AccountController(Controller):
    path = "/api/accounts"

    @post("/")
    async def create_account(self, data: AccountCreate, task_queues: TaskQueues) -> Account:
        user = await self.create(data)
        await task_queues.get("default").enqueue(
            "send_welcome_email",
            user_id=user.id, email=user.email, name=user.name,
            timeout=30, retries=2, key=f"welcome-{user.id}",
        )
        return user
```

```python
# tests/test_accounts.py
async def test_account_creation_queues_welcome_email(client, email_service):
    resp = await client.post("/api/accounts", json={"email": "alice@example.com", "name": "Alice"})
    assert resp.status_code == 201
    # After SAQ flush in test:
    assert len(email_service.outbox) == 1
    assert email_service.outbox[0].subject == "Welcome, Alice!"
```

</example>

---

## Cross-References

- **[litestar](../litestar/SKILL.md)** — DI, plugin lifecycle.
- **[litestar-saq](../litestar-saq/SKILL.md)** — Background-queue email sends.
- **[litestar-testing](../litestar-testing/SKILL.md)** — Testing flows that send email.

## Official References

- <https://github.com/litestar-org/litestar-email>

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
