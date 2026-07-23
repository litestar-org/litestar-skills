# Inertia Protocol & Client-Side Reference

## Inertia Protocol

Inertia bridges server-side routing with client-side rendering:

1. **Initial Request**: Server returns full HTML with page data
2. **Subsequent Requests**: XHR with `X-Inertia` header, server returns JSON
3. **Page Component**: Client renders component with props from server

## React Adapter

```tsx
// app.tsx - Setup
import { createInertiaApp } from "@inertiajs/react"
import { createRoot } from "react-dom/client"
import { csrfHeaders } from "litestar-vite-plugin/helpers"
import { resolvePageComponent } from "litestar-vite-plugin/inertia-helpers"

createInertiaApp({
  resolve: (name) => resolvePageComponent(
    `./pages/${name}.tsx`,
    import.meta.glob("./pages/**/*.tsx"),
  ),
  defaults: {
    visitOptions: (_href, options) => ({
      headers: csrfHeaders(options.headers ?? {}),
    }),
  },
  setup({ el, App, props }) {
    createRoot(el).render(<App {...props} />)
  },
})
```

```tsx
// pages/Users/Index.tsx
import { Head, Link, usePage } from "@inertiajs/react"

interface Props { users: User[] }

export default function UsersIndex({ users }: Props) {
  return (
    <>
      <Head title="Users" />
      <h1>Users</h1>
      {users.map(user => (
        <Link key={user.id} href={`/users/${user.id}`}>{user.name}</Link>
      ))}
    </>
  )
}
```

## Vue Adapter

```ts
// app.ts
import { createApp, h } from "vue"
import { createInertiaApp } from "@inertiajs/vue3"

createInertiaApp({
  resolve: (name) => {
    const pages = import.meta.glob("./pages/**/*.vue", { eager: true })
    return pages[`./pages/${name}.vue`]
  },
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) }).use(plugin).mount(el)
  },
})
```

```vue
<!-- pages/Users/Index.vue -->
<script setup lang="ts">
import { Head, Link } from "@inertiajs/vue3"
defineProps<{ users: User[] }>()
</script>

<template>
  <Head title="Users" />
  <h1>Users</h1>
  <Link v-for="user in users" :key="user.id" :href="`/users/${user.id}`">
    {{ user.name }}
  </Link>
</template>
```

## Forms

```tsx
import { useForm } from "@inertiajs/react"

function CreateUser() {
  const { data, setData, post, processing, errors } = useForm({
    name: "",
    email: "",
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    post("/users")
  }

  return (
    <form onSubmit={submit}>
      <input value={data.name} onChange={e => setData("name", e.target.value)} />
      {errors.name && <span>{errors.name}</span>}
      <button type="submit" disabled={processing}>Create</button>
    </form>
  )
}
```

## Shared Data

```tsx
import { usePage } from "@inertiajs/react"

function Layout({ children }) {
  const { auth, flash } = usePage().props
  return (
    <div>
      {flash.success && <Alert>{flash.success}</Alert>}
      {auth.user ? <span>{auth.user.name}</span> : <Link href="/login">Login</Link>}
      {children}
    </div>
  )
}
```

## Partial Reloads

```tsx
import { router } from "@inertiajs/react"

router.reload({ only: ["users"] })
router.reload({ preserveScroll: true })
router.reload({ preserveState: true })
```

The client sends `X-Inertia-Partial-Component` with `X-Inertia-Partial-Data`
and/or `X-Inertia-Partial-Except`. The server filters only when the component
matches. Except wins when the same key appears in both sets. Initial responses
advertise deferred groups; partial responses omit `deferredProps`.

## Lazy Loading Props (server side)

```python
def get_users():
    return InertiaResponse({
        "users": lazy("users", fetch_users),
        "stats": defer("stats", fetch_stats),
    })
```

The route must declare `component="Users/Index"`. `lazy()` loads only when
explicitly requested; `defer()` advertises a post-render deferred group.

## Asset Versions

Each page includes the asset-loader version and responses expose
`X-Inertia-Version`. When a stale version arrives on an Inertia `GET`, the
middleware returns `409` with `X-Inertia-Location` so the client performs a
full refresh. Non-`GET` submissions continue normally and keep their body.

## SSR Setup

```tsx
// ssr.tsx
import { createInertiaApp } from "@inertiajs/react"
import createServer from "@inertiajs/react/server"
import { renderToString } from "react-dom/server"
import { resolvePageComponent } from "litestar-vite-plugin/inertia-helpers"

const pages = import.meta.glob("./pages/**/*.tsx")

createServer(async (page) => createInertiaApp({
  page,
  render: renderToString,
  resolve: (name) => resolvePageComponent(`./pages/${name}.tsx`, pages),
  setup: ({ App, props }) => <App {...props} />,
}))
```

## Best Practices

- Use `preserveState` for filter/pagination changes
- Use `only` for partial reloads to reduce payload
- Use `lazy` for expensive props that aren't always needed
- Use `defer` for non-critical data that can load after first render
- Handle flash messages in a layout component
- Use the `Head` component for SEO
