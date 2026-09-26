# litestar-security — Composition Reference

A Litestar application rarely contains only its own handlers. Static assets, a
schema browser, and a debug toolbar can arrive as routes another plugin
registered — and none of them carry an `auth` policy.

With mechanisms configured, a route declaring no policy compiles to implicit
`required()`. **A freshly added static files router answers `401` until it is
excluded.**

## This Is Litestar's Behavior

Plain Litestar does the same. An application using `JWTAuth` without an
exclusion also answers `401` for `/static/app.css` — the authentication
middleware runs for every path it is not told to skip. Litestar's answer is the
middleware's `exclude` argument, and `exclude` on `SecurityConfig` is the same
mechanism spelled the same way.

Litestar's other escape hatch, the `exclude_from_auth` opt (configurable via
`SecurityConfig.exclude_opt_key`), is also honored across all ownership layers
(handler, controller, router, or application) by truthiness, with the innermost
owner winning:

- A handler under an excluded router or controller can opt back into
  authentication with `opt={"exclude_from_auth": False}` or an explicit `auth=`
  policy.
- Declaring both `auth` and a truthy `exclude_from_auth` on the **same**
  ownership layer is rejected at startup (`Route declares both auth and exclude_from_auth`).
- For routers built by third-party plugins whose `opt` you do not control, use
  `SecurityConfig(exclude=[...])` path patterns.

## Excluding Paths

`exclude` accepts one regular expression or a sequence of them:

```python
from litestar import Litestar
from litestar.static_files import create_static_files_router

from litestar_security import SecurityConfig, SecurityPlugin

config = SecurityConfig(exclude=["^/static", "^/assets"])

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
| `litestar-asyncapi` | AsyncAPI document and its UI | `^` + configured schema path |
| `debug-toolbar` | Toolbar panels and assets | `^` + configured toolbar path |

Confirm against the routes the built application actually registers:

```python
for route in app.routes:
    print(route.path)
```

## Inspecting Route Posture

Use the CLI command to inspect the compiled security posture across all registered routes:

```bash
LITESTAR_APP=app:app litestar security routes
```

This displays a table containing each route's Path, Method, Policy (`required`, `optional`, `public`, `exclude`), Auth status, CSRF enforcement, and inherited Guards. It also warns if an excluded route carries inherited guards that would still deny access.

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

## Machine-Only Plugin Surfaces (e.g. `litestar-mcp`)

Machine surfaces like `/mcp` authenticate with API keys or IAP assertions and
have no browser cookie to pair with a CSRF header. Restricting their policy to
non-session mechanisms (`required("api-key", "google-iap")` or
`required(mechanism("api-key"))`) keeps the surface fail-closed while making
`SecurityPlugin` derive the browser CSRF exemption automatically.

You can pass `route_opt={"auth": required(mechanism("api-key"))}` directly on
`MCPConfig` (or `opt = {"auth": required(mechanism("api-key"))}` on a dedicated
MCP controller), or stamp `AUTH_POLICY_OPT_KEY` on `/mcp` handlers via an
`InitPluginProtocol` before `SecurityPlugin` compiles routes:

```python
from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol
from litestar.router import Router
from litestar.routes import HTTPRoute
from litestar_security.authentication import AUTH_POLICY_OPT_KEY, required


class MCPRoutePolicy(InitPluginProtocol):
    __slots__ = ("base_path", "iap_enabled")

    def __init__(self, *, base_path: str = "/mcp", iap_enabled: bool = False) -> None:
        self.base_path = base_path
        self.iap_enabled = iap_enabled

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        policy = required("api-key", "google-iap") if self.iap_enabled else required("api-key")
        for registered in app_config.route_handlers:
            if not (isinstance(registered, Router) and registered.path == self.base_path):
                continue
            for route in registered.routes:
                if isinstance(route, HTTPRoute):
                    for handler in route.route_handlers:
                        handler.opt[AUTH_POLICY_OPT_KEY] = policy
        return app_config
```

## Cross-References

- **[Authentication](authentication.md)** — the policy helpers and ownership layers.
- **[Litestar plugins](../../litestar/references/plugins.md)** — plugin registration order and init hooks.

## Official References

- <https://github.com/cofin/litestar-security/blob/v0.6.0/docs/composition.rst>
