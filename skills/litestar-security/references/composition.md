# litestar-security — Composition Reference

A Litestar application rarely contains only its own handlers. Static assets, a
queue dashboard, a schema browser, and a debug toolbar all arrive as routes
another plugin registered — and none of them carry an `auth` policy.

With mechanisms configured, a route declaring no policy compiles to implicit
`required()`. **A freshly added static files router answers `401` until it is
excluded.**

## This Is Litestar's Behavior

Plain Litestar does the same. An application using `JWTAuth` without an
exclusion also answers `401` for `/static/app.css` — the authentication
middleware runs for every path it is not told to skip. Litestar's answer is the
middleware's `exclude` argument, and `exclude` on `SecurityConfig` is the same
mechanism spelled the same way.

Litestar's other escape hatch, the `exclude_from_auth` opt, is deliberately
narrower here: honored on an individual route handler, **rejected** on a
router, controller, or application, because a layer-level exclusion opens a
whole subtree without naming what is in it. Routers built by another plugin
expose `opt` only at the router level, so path patterns are the route to take.

## Excluding Paths

`exclude` accepts one regular expression or a sequence of them:

```python
from litestar import Litestar
from litestar.static_files import create_static_files_router

from litestar_security import SecurityConfig, SecurityPlugin

config = SecurityConfig(
    mechanisms=[api_key_mechanism],
    exclude=["^/static", "^/assets"],
)

app = Litestar(
    route_handlers=[
        api_router,
        create_static_files_router(path="/static", directories=["public"]),
    ],
    plugins=[SecurityPlugin(config)],
)
```

Patterns match the **route path as Litestar registered it**, not the request
URL. A static files router mounted at `/static` registers
`/static/{file_path:path}`, which `^/static` matches.

Exclusion is total: an excluded route is not authenticated, receives no
principal, and contributes an anonymous security requirement to OpenAPI rather
than the configured schemes. That is why the pattern is applied at route
compilation rather than per request — a runtime-only bypass would leave the
OpenAPI document claiming a route is protected when it is not.

> **Warning:** `exclude` removes authentication from every route it matches.
> Write the narrowest pattern that covers the mount point, and anchor it
> with `^`.

## What the Compiler Checks

Patterns are anchored at the start of the route path. `"^/static"` and
`"/static"` both exclude `/static/{file_path:path}`; a bare `"static"` does
not, because it does not match from position zero. Litestar's runtime
middleware searches anywhere in the path instead, so a pattern Litestar would
treat as matching mid-path leaves the route protected here — the difference
only ever resolves toward keeping a route authenticated.

A route that declares its own `auth` **and** matches an exclusion pattern is
rejected at startup:

```text
Route declares auth but matches a security exclusion pattern for GET /assets/report
```

Policy resolves through ownership layers, so an application-wide
`opt={"auth": ...}` counts as a declaration for every route beneath it,
including excluded ones. **Scope that default to the router owning the
application's own routes** and let policy-less routes take the implicit
default.

A pattern matching no registered route is reported once at startup:

```text
LitestarWarning: Litestar Security exclusion patterns match no registered route: ^/nowhere
```

It warns rather than raises — a pattern written for a route that exists only in
production, or only when an optional plugin is installed, stays legitimate.

## Patterns per Plugin

Read the mount path off the plugin's own configuration rather than assuming a
default.

| Plugin | Registers | Pattern |
| --- | --- | --- |
| `litestar-vite` | Static route for the built bundle, plus the dev proxy | `^` + configured asset URL, e.g. `"^/static"` |
| `litestar-saq` | Queue dashboard router and its API | `^` + configured web path, e.g. `"^/saq"` |
| `litestar-queues` | Queue management and status routes | `^` + configured route prefix |
| `litestar-asyncapi` | AsyncAPI document and its UI | `^` + configured schema path |
| `debug-toolbar` | Toolbar panels and assets | `^` + configured toolbar path |

Confirm against the routes the built application actually registers:

```python
for route in app.routes:
    print(route.path)
```

## Leaving a Plugin's Routes Protected

Excluding is a choice, not an obligation — a dashboard is often exactly what
should stay behind authentication. Leaving it out of `exclude` keeps the
implicit `required()`. To give it a policy of its own, wrap the plugin's router:

```python
from litestar import Router

from litestar_security import required

operations = Router(path="/", route_handlers=[queue_router], opt={"auth": required("session")})
```

Because the wrapper declares a policy, the wrapped routes must not also match
an exclusion pattern.

## Cross-References

- **[Authentication](authentication.md)** — the policy helpers and ownership layers.
- **[litestar-plugins](../../litestar-plugins/SKILL.md)** — plugin registration order and init hooks.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.3.0/docs/composition.rst>
