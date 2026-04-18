# Google Developer Knowledge MCP

Optional MCP server that returns fresh Google developer documentation (Firebase / Google Cloud / Android / Maps) from `developerknowledge.googleapis.com`. Useful when a Litestar project depends on a Google-managed service and you want authoritative doc lookups inline with code review or planning.

Primary source: <https://developers.google.com/knowledge/mcp>.

## What it provides

| Attribute | Value |
| --- | --- |
| Server URL | `https://developerknowledge.googleapis.com/mcp` (HTTP transport) |
| Tools | `search_documents`, `get_documents`, `answer_query` (preview — may change) |
| Indexed domains | Firebase, Google Cloud, Android, Google Maps |
| Coverage | Publicly visible pages only; English-only |
| Supported hosts (Google-documented) | Gemini CLI, Gemini Code Assist, Claude Code, Cursor, GitHub Copilot, Windsurf, Google Antigravity |

## Auth

Two options. Pick API key for simplicity; OAuth only if your org mandates it.

**API key (recommended).** Generate a key at `https://console.cloud.google.com/apis/credentials`, restrict it to the Developer Knowledge API, and pass it as the `X-Goog-Api-Key` header. Rotate the key like any other secret; do not commit it to the repo.

**OAuth via Application Default Credentials.** `gcloud auth application-default login` on the host machine; the MCP client picks up ADC automatically.

Enable the API once per GCP project:

```bash
gcloud beta services mcp enable developerknowledge.googleapis.com --project=PROJECT_ID
```

## Per-host install

**Claude Code:**

```bash
claude mcp add google-dev-knowledge --transport http \
  https://developerknowledge.googleapis.com/mcp \
  --header "X-Goog-Api-Key: YOUR_API_KEY"
```

**Gemini CLI:**

```bash
gemini mcp add -t http -H "X-Goog-Api-Key: YOUR_API_KEY" \
  google-developer-knowledge \
  https://developerknowledge.googleapis.com/mcp --scope user
```

Other documented hosts (Cursor, GitHub Copilot, Windsurf, Antigravity) follow each host's generic MCP add flow with the same URL + header.

## When to use it

Use this MCP server when the question is **specifically about a Google product** and recency matters — release notes, new SDK methods, deprecations, pricing. For everything else, the `flow:apilookup` skill covers general API/framework lookups without requiring a GCP project.

Rule of thumb: if the question references Firebase, Cloud Run, GKE, BigQuery, AlloyDB, Android SDK, or Google Maps API, reach for this MCP server first. If it's about Litestar, msgspec, SQLAlchemy, or other non-Google ecosystem libraries, reach for `flow:apilookup` instead.

## Known gaps

- **Codex CLI** and **OpenCode** are **not** in Google's documented host list for this MCP server. They may still work via generic HTTP-MCP client support, but upstream does not verify or support those combinations.
- `answer_query` is marked preview by Google and may be removed or renamed without notice; prefer `search_documents` + `get_documents` for stable workflows.
- Coverage is English-only and excludes private / restricted Google docs (`console.cloud.google.com` internal surfaces, pre-launch previews).

## Not shipped

This repo **does not** ship an MCP manifest that hardcodes the server or an API key. Users opt in per-host using the commands above. No `.claude-plugin/mcp.json`, no `gemini-extension.json` MCP block, no `.opencode/mcp.toml` entries reference this server.

Rationale: the MCP server requires a user-provided GCP API key; bundling a manifest would either hardcode a secret or ship broken defaults. The opt-in reference-file pattern matches how this repo handles other optional integrations.
