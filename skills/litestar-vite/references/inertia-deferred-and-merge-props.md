# litestar-vite — Inertia Deferred, Partial & Merge Props

Reference for partial reloads, deferred/lazy/once/always/merge prop wrappers, pagination containers, and infinite scroll in `litestar_vite.inertia`. See [Inertia Reference](inertia.md) for core setup and [Advanced Inertia Patterns](inertia-advanced-patterns.md) for Precognition, exception handling, and `InertiaRequest`.

## Partial Reloads & Prop Filters

Client-side partial reloads request or exclude specific props on the same page component:

```tsx
import { router } from "@inertiajs/react"

router.reload({ only: ["users"] })
router.reload({ except: ["stats"] })
router.reload({ reset: ["items"] })
router.reload({ preserveScroll: true, preserveState: true })
```

Protocol rules:

- `X-Inertia-Partial-Data` and `X-Inertia-Partial-Except` apply only when `X-Inertia-Partial-Component` matches the route's component.
- `X-Inertia-Partial-Data` includes requested keys; `X-Inertia-Partial-Except` excludes keys and wins on overlap.
- Initial responses advertise `deferredProps` metadata. Partial responses omit `deferredProps` entirely, including unrequested groups.
- Server-side `only("key1", "key2")` and `except_("internalKey")` can also be passed via `InertiaResponse(..., prop_filter=...)`.

## Prop Wrapper Helpers

`InertiaPlugin` wraps Inertia route handlers so async callbacks inside `defer()`, `optional()`, `lazy()`, and `once()` (including in shared props) are awaited via `resolve_async_props()` **inside** Litestar's DI `AsyncExitStack` frame while request-scoped database sessions (`advanced-alchemy`, `sqlspec`) remain open.

| Helper | Protocol Role |
| --- | --- |
| `always("key", value)` | Always included in every response, bypassing `only` and `except` filters |
| `once("key", value_or_fn)` | Evaluated on initial visit, advertised in `onceProps`, and cached client-side; omitted when `X-Inertia-Except-Once-Props` includes the key unless forced via `only` or `X-Inertia-Reset` |
| `defer("key", fn, group="default")` | Excluded on initial visit and advertised in `deferredProps[group]`; fetched automatically by the client after mount. Chain `.once()` (`defer(...).once()`) to also cache across visits |
| `optional("key", fn)` | Excluded from initial visit and standard reloads; evaluated only when explicitly requested in `X-Inertia-Partial-Data` (`only: ['key']`, e.g. `<WhenVisible>`) |
| `lazy("key", value_or_fn)` | Excluded from initial visit; evaluated only when requested in `X-Inertia-Partial-Data` |
| `merge("key", value, strategy="append"\|"prepend"\|"deep", match_on=None)` | Advertised in `mergeProps`, `prependProps`, or `deepMergeProps` (plus `matchPropsOn` for deduplication) so the client merges array/object state across visits |

```python
from litestar import get
from litestar_vite.inertia import (
    InertiaResponse,
    always,
    defer,
    except_,
    lazy,
    merge,
    once,
    only,
    optional,
    scroll_props,
)


@get("/reports", component="reports/Index")
async def reports_page(reports_service) -> InertiaResponse:
    """Demonstrate all Inertia prop wrapper helpers."""
    return InertiaResponse(
        content={
            "summary": await reports_service.summary(),
            "auth": always("auth", {"canEdit": True}),
            "settings": once("settings", reports_service.get_settings),
            "comments": optional("comments", reports_service.get_comments),
            "export": lazy("export", reports_service.export),
            "stats": defer("stats", reports_service.fetch_stats, group="analytics").once(),
            "items": merge("items", await reports_service.list_items(), strategy="append", match_on="id"),
        },
        prop_filter=only("summary", "auth", "settings", "comments", "export", "stats", "items"),
    )


@get("/users", component="Users/Index")
async def users_page(user_service) -> InertiaResponse:
    """Render users page with scroll metadata and except_ filter."""
    return InertiaResponse(
        content={
            "users": await user_service.list_users(),
            "feed": merge("feed", await user_service.fetch_feed(), strategy="append", match_on="id"),
        },
        scroll_props=scroll_props(page_name="page", current_page=1, next_page=2),
        prop_filter=except_("internalDebug"),
    )
```

### Callable & Session Handoff Rules

- **Pass callables, not invoked results, to `lazy`, `defer`, `optional`, and `once`** — write `defer("stats", fetch_stats)` or `defer("stats", lambda: fetch_stats(user_id))`, never `defer("stats", fetch_stats())` which executes eagerly on every request.
- **Do not stage async special props in `share()` before a redirect** — session handoff on `InertiaRedirect` / `InertiaBack` is synchronous and drops unawaited async callables; use async shared props only on direct `InertiaResponse` renders.

## Structured Prop Bags with `DeferredProp`

Top-level fields of `msgspec.Struct`, `@dataclass`, and Pydantic models are extracted shallowly so nested `DeferredProp` and `StaticProp` wrappers stay intact and preserve `rename="camel"` field aliases:

```python
import msgspec
from litestar import get
from litestar_vite.inertia import defer
from litestar_vite.inertia.helpers import DeferredProp


class ProjectSummary(msgspec.Struct, rename="camel"):
    """Serialized project summary."""

    project_id: int
    display_name: str


class ProjectsPageProps(msgspec.Struct, rename="camel"):
    """Structured prop bag with a deferred analytics prop."""

    projects: list[ProjectSummary]
    analytics: DeferredProp[dict[str, int]]


@get("/projects", component="Projects/Index")
async def list_projects(project_service) -> ProjectsPageProps:
    """Return a msgspec Struct directly as Inertia page props."""
    return ProjectsPageProps(
        projects=await project_service.list_summaries(),
        analytics=defer("analytics", project_service.compute_analytics),
    )
```

## Pagination & Infinite Scroll

When a handler returns `OffsetPagination`, `ClassicPagination`, or `ScrollPagination` (or any `PaginationContainer`), `InertiaResponse` extracts the items list into `props[key]` (default `"items"`, configurable via route `key="posts"`), flattens pagination metadata (`total`, `limit`, `offset`, `currentPage`, `totalPages`, `pageSize`) as camelCase sibling props, and—when `infinite_scroll=True` is set on the route—populates `scrollProps[key]` (`pageName`, `currentPage`, `previousPage`, `nextPage`).

```python
from litestar import get
from litestar.pagination import OffsetPagination


@get("/feed", component="Feed/Index", infinite_scroll=True, key="posts")
async def feed_page(feed_service, page: int = 1, limit: int = 20) -> OffsetPagination[ProjectSummary]:
    """Return OffsetPagination with automatic scrollProps metadata."""
    return await feed_service.paginate(page=page, limit=limit)
```

Client-side TypeScript helpers exported from `litestar-vite-plugin/inertia-helpers`:

- `OffsetPaginationProps<T>`: `{ items: T[], total: number, limit: number, offset: number }`
- `ClassicPaginationProps<T>`: `{ items: T[], currentPage: number, totalPages: number, pageSize: number }`
- `CursorPaginationProps<T>`: `{ items: T[], total?: number, hasMore?: boolean, hasNext?: boolean, hasPrevious?: boolean, nextCursor?: string | null, previousCursor?: string | null }`
- `ScrollProps`: `{ pageName: string, currentPage: number, previousPage: number | null, nextPage: number | null }` (emitted under `scrollProps[key]` when `infinite_scroll=True`)
