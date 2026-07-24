# github-org-mcp

A stateless HTTP **MCP service** that exposes **GitHub organization member management** (list / view / add / update role / remove members, and manage invitations) as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools consumable by Claude and other MCP clients.

The OAuth flow is handled **upstream** — this service does not perform OAuth. The caller passes a GitHub **OAuth access token** and the **org slug** on each request via HTTP headers; the service maps the token to `Authorization: Bearer <token>` when calling the GitHub REST API.

## Architecture

- **Stateless** — no user state, no credential storage, no session data persisted between requests.
- **Concurrent-safe** — per-request credential isolation via Python `contextvars`; concurrent requests never bleed token/org.
- **Dual auth modes** — per-request credentials via HTTP headers (`gateway` mode, default, SOP-compliant) or single shared credentials (`env` mode, local dev only).
- **Two transports** — HTTP server (`MCP_TRANSPORT=http`) for production, stdio (`MCP_TRANSPORT=stdio`) for local development.

## Endpoints

| Method | Path      | Description              |
|--------|-----------|--------------------------|
| POST   | `/mcp`    | MCP protocol entry point |
| GET    | `/health` | Health check             |

Default port: **8080** (configurable via `MCP_HTTP_PORT`).

## Authentication — HEADER Parameters

In `gateway` mode (default), every `POST /mcp` request must carry **both** headers below. Requests missing either header receive `401`. Credentials are never stored globally or persisted; each request's token and org live only in a `contextvars.ContextVar` and are reset when the request completes.

| Client → this service | this service → GitHub upstream |
|---|---|
| `X-GitHub-Token: <oauth_access_token>` | `Authorization: Bearer <oauth_access_token>` |
| `X-GitHub-Org: <org_slug>` | URL path segment `.../orgs/<org_slug>/...` |

| Header | 类型 (Type) | 是否必填 (Required) | 默认值 (Default) | 枚举值 (Enum) | 字段描述 (Description) | Example |
|---|---|---|---|---|---|---|
| `X-GitHub-Token` | string | 必填 (Yes) | 无 (none) | 无 (none) | GitHub OAuth access token; mapped to `Authorization: Bearer`. OAuth flow handled upstream. | `gho_16C7e42F292c6912E7710c838347Ae178B4a` |
| `X-GitHub-Org` | string | 必填 (Yes) | 无 (none) | 无 (none) | GitHub organization login/slug the tools operate on. | `my-company` |

> The header names are configurable via `GITHUB_TOKEN_HEADER` / `GITHUB_ORG_HEADER`.

### Service Parameters

| Variable             | Required      | Default                  | Description                                                                               |
|----------------------|---------------|--------------------------|-------------------------------------------------------------------------------------------|
| `AUTH_MODE`          | No            | `gateway`                | `gateway` (per-request credentials, SOP-compliant) or `env` (shared credentials, dev only) |
| `GITHUB_TOKEN_HEADER`| No            | `X-GitHub-Token`         | HTTP header carrying the OAuth token in `gateway` mode                                     |
| `GITHUB_ORG_HEADER`  | No            | `X-GitHub-Org`           | HTTP header carrying the org slug in `gateway` mode                                        |
| `GITHUB_TOKEN`       | env mode only | —                        | OAuth access token used in `env` mode (local dev only)                                    |
| `GITHUB_ORG`         | env mode only | —                        | Org slug used in `env` mode (local dev only)                                              |
| `GITHUB_BASE_URL`    | No            | `https://api.github.com` | GitHub REST API base URL (change for GitHub Enterprise Server)                            |
| `MCP_TRANSPORT`      | No            | `stdio`                  | Transport: `http` or `stdio`                                                              |
| `MCP_HTTP_PORT`      | No            | `8080`                   | HTTP listen port                                                                          |
| `MCP_HTTP_HOST`      | No            | `0.0.0.0`                | HTTP listen host                                                                          |

### Auth Modes

**`gateway` mode** (default, production, SOP-compliant):
- Each request must include the `X-GitHub-Token` and `X-GitHub-Org` headers.
- No credentials are stored globally — isolated per request via Python `contextvars`.
- Returns `401` if either header is missing.

> **`env` mode** (local dev only — **not SOP-compliant for production**):
> - Set `AUTH_MODE=env`, `GITHUB_TOKEN`, and `GITHUB_ORG` in the environment or `.env`.
> - All requests share the same credentials loaded at startup — violates per-request credential isolation.
> - Do not use in production or multi-tenant deployments.

## Tool List

All tools follow the naming convention `github_<action>_<resource>` and operate on the org resolved from the request context (`X-GitHub-Org`).

| Tool | Description | Parameters |
|---|---|---|
| `github_list_org_members` | List members of the organization | `role` (str, `all`/`admin`/`member`, default `all`), `filter` (str, `all`/`2fa_disabled`, default `all`), `per_page` (int, default 30), `page` (int, default 1) |
| `github_get_org_membership` | Get a user's membership role and state | `username` (str, required) |
| `github_set_org_membership` | Add a user to the org or update their role (invites if not a member) | `username` (str, required), `role` (str, `member`/`admin`, default `member`) |
| `github_remove_org_member` | Remove a user from the org (also removes from all teams) | `username` (str, required) |
| `github_list_org_invitations` | List pending member invitations | `per_page` (int, default 30), `page` (int, default 1) |
| `github_create_org_invitation` | Invite a user by user ID or email | `invitee_id` (int, optional), `email` (str, optional), `role` (str, `direct_member`/`admin`/`billing_manager`, default `direct_member`), `team_ids` (list[int], optional) — exactly one of `invitee_id`/`email` |
| `github_cancel_org_invitation` | Cancel a pending invitation | `invitation_id` (int, required) |

> The token's OAuth scopes / org permissions determine which operations succeed. Write operations (`set`/`remove`/`create`/`cancel`) require the token to belong to an org owner or an app with the appropriate org-members permission.

## Quick Start

### Local development (stdio)

```bash
cp .env.example .env
# Edit .env: set GITHUB_TOKEN, GITHUB_ORG, AUTH_MODE=env, MCP_TRANSPORT=stdio
uv sync
python -m github_org_mcp
```

### HTTP server (gateway mode — default, SOP-compliant)

```bash
MCP_TRANSPORT=http python -m github_org_mcp
# Pass credentials per-request via X-GitHub-Token and X-GitHub-Org headers
```

### Docker

```bash
docker compose up --build
```

## Test Examples

### Health check

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{"status": "ok", "transport": "http", "auth_mode": "gateway"}
```

### Missing headers → 401 (gateway mode)

```bash
curl -i -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# → HTTP/1.1 401, body includes "required_headers": ["X-GitHub-Token", "X-GitHub-Org"]
```

### List MCP tools

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-GitHub-Token: your_oauth_access_token" \
  -H "X-GitHub-Org: my-company" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Call a tool — list org members

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-GitHub-Token: your_oauth_access_token" \
  -H "X-GitHub-Org: my-company" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "github_list_org_members",
      "arguments": {"role": "all", "per_page": 30, "page": 1}
    }
  }'
```

### Call a tool — invite a user by email

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-GitHub-Token: your_oauth_access_token" \
  -H "X-GitHub-Org: my-company" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "github_create_org_invitation",
      "arguments": {"email": "newhire@example.com", "role": "direct_member"}
    }
  }'
```

## Security

- Credentials are never stored globally or persisted between requests.
- Each request's token and org are isolated in `contextvars.ContextVar` and reset after the request completes.
- The service runs as a non-root user (`github`, uid 1001) inside the container.
- Never commit real tokens or org secrets — `.gitignore` excludes `.env`.
