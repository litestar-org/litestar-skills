---
name: litestar-realtime
description: "Auto-activate for @websocket, websocket_listener, websocket_stream, WebSocket, ServerSentEvent, ChannelsPlugin, AsyncPgChannelsBackend, RedisChannelsPubSubBackend, SQLSpecChannelsBackend, or fan-out. Not for polling APIs."
---

# Litestar Realtime

Use this skill for WebSockets, SSE, ChannelsPlugin backends, realtime event contracts, and fan-out from workers or services.

## Code Style Rules

- Use plain WebSocket handlers for one-off streams.
- Use ChannelsPlugin when dynamic topics, history, or cross-process fan-out matter.
- Choose the backend that matches the existing stack.
- Treat WebSocket auth separately from HTTP header auth constraints.

## Quick Reference

- WebSocket and Channels patterns: [websockets.md](references/websockets.md)
- Event contract patterns: [realtime-events.md](references/realtime-events.md)
- Pair with [litestar-auth-guards](../litestar-auth-guards/SKILL.md) for socket auth.

<workflow>

## Workflow

1. Choose WebSocket, SSE, or Channels based on delivery needs.
2. Define event contracts before wiring transport.
3. Select a backend that fits the project stack.
4. Test connection, auth, fan-out, disconnect, and error paths.

</workflow>

<guardrails>

## Guardrails

- Do not force Redis into a PostgreSQL-only stack just for Channels.
- Do not assume browsers can set arbitrary WebSocket headers.
- Do not publish untyped event dicts across service boundaries.
- Do not use request-scoped resources after the socket lifecycle ends.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Transport choice matches the user experience.
- [ ] Event payloads are typed.
- [ ] Backend choice matches the stack.
- [ ] Auth and disconnect behavior are tested.

</validation>

<example>

## Example

```python
from litestar import websocket

@websocket("/ws")
async def stream(socket: WebSocket) -> None:
    await socket.accept()
    await socket.send_json({"type": "ready"})
```

</example>

## References Index

- [websockets.md](references/websockets.md)
- [realtime-events.md](references/realtime-events.md)

## Official References

- <https://docs.litestar.dev/> - Litestar documentation
- <https://docs.litestar.dev/latest/reference/> - Litestar API reference

## Shared Styleguide Baseline

- [General](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
