# litestar-vite — Advanced Inertia Patterns

Reference for Laravel Precognition validation, automatic exception handling, browser history encryption, `InertiaRequest` inspection, asset version conflict handling, SSR circuit breakers, and end-to-end controller + page workflows. See [Inertia Reference](inertia.md) for core setup and [Deferred, Partial & Merge Props](inertia-deferred-and-merge-props.md) for prop wrappers.

## Precognition (Real-Time Form Validation)

Enable `InertiaConfig(precognition=True)` and decorate form handlers with `@precognition`:

1. Client sends a request with `Precognition: true` (and optionally `Precognition-Validate-Only: name,email`).
2. If DTO validation succeeds, the server returns `204 No Content` with `Precognition-Success: true` (`PrecognitionResponse`) and skips the handler body.
3. If validation fails, the server returns `422 Unprocessable Entity` with `Precognition: true` and `{ message, errors: Record<string, string[]> }` formatted for `laravel-precognition-*` clients.

```python
from litestar import Request, post
from litestar_vite.inertia import InertiaConfig, InertiaRedirect, precognition

inertia_config = InertiaConfig(precognition=True)


@post("/projects")
@precognition
async def create_project(data: ProjectCreateDTO, request: Request) -> InertiaRedirect:
    """Create a project for a non-Precognition submission."""
    await project_service.create(data)
    return InertiaRedirect(request, "/projects")
```

Client-side utilities exported from `litestar-vite-plugin/inertia-helpers`:

- `PrecognitionHeaders` (`PRECOGNITION`, `PRECOGNITION_SUCCESS`, `VALIDATE_ONLY`)
- `isPrecognitionSuccess(response: Response): boolean`
- `isPrecognitionError(response: Response): boolean`
- `extractPrecognitionErrors(response: Response): Promise<PrecognitionValidationErrors>`
- Types: `PrecognitionValidationErrors`, `PrecognitionFormConfig`

## Automatic Exception Handling & Scoped Error Bags

`InertiaPlugin` registers `exception_to_http_response` for `Exception` and `HTTPException` (plus `AdvancedAlchemyRepositoryError` and `SQLSpecRepositoryError` when installed):

- **`ValidationException` (422), `HTTP_400_BAD_REQUEST`, and `PermissionDeniedException` (403)** on Inertia routes automatically flash the exception detail (`category="error"`), extract field-level errors from `exc.extra` via `error(request, field, message)`, and return `InertiaBack(request)`.
- **Scoped error bags**: When the client sends `X-Inertia-Error-Bag: createUser` (e.g. `post("/users", { errorBag: "createUser" })`), `get_shared_props` automatically namespaces validation errors under `props["errors"]["createUser"]`.
- **`NotAuthorizedException` (401)** redirects to `InertiaConfig.redirect_unauthorized_to` when configured (falling back to `?error=<detail>` when no writable session exists).
- **`NotFoundException` (404/405)** redirects to `InertiaConfig.redirect_404` when configured.

## History Encryption & Asset Version Conflicts

- **History encryption**: Enable globally via `InertiaConfig(encrypt_history=True)` or per response via `InertiaResponse(..., encrypt_history=True)` so the client encrypts browser history state via the Web Crypto API. Clear history state on logout or login transitions via `clear_history(request)` or `InertiaResponse(..., clear_history=True)`.
- **Asset version conflict (`409`)**: Each page includes the asset version hash from `ViteAssetLoader` and responses expose `X-Inertia-Version`. When a stale version arrives on an Inertia `GET`, middleware returns `409 Conflict` with `X-Inertia-Location` so the client performs a full window reload. Non-`GET` submissions proceed to their handlers normally so form payloads are not lost.

```python
from litestar import Request, get, post
from litestar_vite.inertia import InertiaBack, InertiaResponse, clear_history


@post("/logout")
async def logout(request: Request) -> InertiaBack:
    """Clear browser history state on logout."""
    clear_history(request)
    return InertiaBack(request)


@get("/login", component="Auth/Login")
async def login_page() -> InertiaResponse:
    """Start a page with a fresh browser history-encryption key."""
    return InertiaResponse(content={}, clear_history=True)
```

## Request Inspection (`InertiaRequest`)

`InertiaPlugin` sets `request_class=InertiaRequest`. Every request exposes:

| Property | Type | Description |
| --- | --- | --- |
| `request.is_inertia` | `bool` | `True` when `X-Inertia: true` header is present |
| `request.inertia_enabled` | `bool` | `True` when `is_inertia` or the route handler defines a `component=` / `page=` opt key |
| `request.is_partial_render` | `bool` | `True` when `X-Inertia-Partial-Component` matches the route's component and partial filter headers are present |
| `request.partial_keys` | `set[str]` | Keys requested via `X-Inertia-Partial-Data` |
| `request.partial_except_keys` | `set[str]` | Keys excluded via `X-Inertia-Partial-Except` |
| `request.except_once_props_keys` | `set[str]` | Cached `once` prop keys excluded via `X-Inertia-Except-Once-Props` |
| `request.reset_keys` | `set[str]` | Prop keys to reset on client state via `X-Inertia-Reset` |
| `request.error_bag` | `str \| None` | Error bag name from `X-Inertia-Error-Bag` |
| `request.merge_intent` | `str \| None` | Infinite-scroll merge direction (`"append"` or `"prepend"`) from `X-Inertia-Infinite-Scroll-Merge-Intent` |
| `request.is_precognition` | `bool` | `True` when `Precognition: true` header is present |
| `request.precognition_validate_only` | `set[str]` | Field subset from `Precognition-Validate-Only` |

## SSR Resilience & Circuit Breaker (`0.32.0+`)

Configure `InertiaSSRConfig` to manage SSR process lifecycle, timeouts, and automatic CSR fallback when the Node SSR worker is unavailable:

```python # pragma: legacy-example
from litestar_vite import InertiaConfig, InertiaSSRConfig

inertia = InertiaConfig(
    ssr=InertiaSSRConfig(
        enabled=True,
        timeout=2.0,
        target_selector="#app",
        fallback_to_client=True,
        circuit_breaker_enabled=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_reset_timeout=30.0,
    ),
)
```

- In development, `TCPStreamIPCTransport` connects to `/__litestar_ssr__` (`litestarViteSsrPlugin` from `litestar-vite-plugin/dev-ssr` using Vite 7+ `ModuleRunner`).
- In production, `StdioIPCTransport` spawns `litestar-vite-ssr-worker`.
- `<!--inertia-head-->` and `<!--inertia-body-->` slot tokens in `root_template` are replaced with SSR head/body output, falling back to `#app`.

## End-to-End Authenticated Controller & Page Example

```python
"""app/domain/projects/controllers.py"""

from __future__ import annotations

from litestar import Controller, Request, get, post
from litestar_vite.inertia import InertiaBack, error, flash

from app.domain.accounts.guards import requires_active_user
from app.domain.projects.schemas import Project, ProjectCreate
from app.domain.projects.services import ProjectService


class ProjectsController(Controller):
    """Projects management controller."""

    path = "/projects"
    guards = [requires_active_user]

    @get("/", component="projects/Index")
    async def index(self, projects_service: ProjectService, request: Request) -> dict[str, list[Project]]:
        """List projects for the current user."""
        return {
            "projects": await projects_service.list_for_user(request.user.id),
        }

    @post("/")
    async def create(
        self,
        data: ProjectCreate,
        projects_service: ProjectService,
        request: Request,
    ) -> InertiaBack:
        """Create a project or return field validation errors on duplicate name."""
        if await projects_service.exists(name=data.name, owner_id=request.user.id):
            error(request, "name", "You already have a project with this name.")
            return InertiaBack(request)

        await projects_service.create(data, owner_id=request.user.id)
        flash(request, "Project created.", category="success")
        return InertiaBack(request)
```

```tsx
// resources/js/pages/projects/Index.tsx
import { useForm, usePage, router } from "@inertiajs/react"
import type { Project } from "@/generated/api"

export default function ProjectsIndex() {
  const {
    props: { projects },
    flash,
  } = usePage<{ projects: Project[] }>()

  const { data, setData, post, processing, errors, reset } = useForm({ name: "", description: "" })

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    post("/projects", { onSuccess: () => reset() })
  }

  return (
    <>
      {flash.success?.map((msg, idx) => (
        <div key={idx} className="flash">{msg}</div>
      ))}

      <form onSubmit={onSubmit}>
        <input value={data.name} onChange={(e) => setData("name", e.target.value)} placeholder="Project name" />
        {errors.name && <div className="error">{errors.name}</div>}
        <textarea value={data.description} onChange={(e) => setData("description", e.target.value)} />
        <button disabled={processing}>Create</button>
      </form>

      <button onClick={() => router.reload({ only: ["projects"] })}>Refresh</button>

      <ul>
        {projects.map((p) => <li key={p.id}>{p.name}</li>)}
      </ul>
    </>
  )
}
```
