import contextvars
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import GitHubClient
from .config import Settings

# ─────────────────────────────────────────────────────────────────────────────
# Per-request credential contextvars for gateway mode.
# GitHubGatewayMiddleware sets these before the MCP handler runs.
# Python asyncio copies context per task, so concurrent requests are isolated —
# no global variables, no persisted credentials (SOP §3/§6).
# ─────────────────────────────────────────────────────────────────────────────
_gateway_token_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "github_gateway_token", default=None
)
_gateway_org_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "github_gateway_org", default=None
)


def get_client_from_context(settings: Settings) -> GitHubClient | None:
    """Resolve the active GitHubClient for the current request context."""
    if settings.auth_mode == "gateway":
        token = _gateway_token_var.get()
        org = _gateway_org_var.get()
    else:
        token = settings.github_token
        org = settings.github_org

    if not token or not org:
        return None
    return GitHubClient(token, org, settings.github_base_url)


class GitHubGatewayMiddleware:
    """ASGI middleware for gateway mode.

    Reads the token and org headers from each request and stores them in
    contextvars for the duration of that request. Returns 401 if either header
    is missing on /mcp requests.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        # Header lookup is case-insensitive in Starlette
        token = request.headers.get(self.settings.github_token_header.lower())
        org = request.headers.get(self.settings.github_org_header.lower())

        missing = []
        if not token:
            missing.append(self.settings.github_token_header)
        if not org:
            missing.append(self.settings.github_org_header)

        if missing:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        "Gateway mode requires the "
                        f"{self.settings.github_token_header} and "
                        f"{self.settings.github_org_header} headers"
                    ),
                    "required_headers": [
                        self.settings.github_token_header,
                        self.settings.github_org_header,
                    ],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _gateway_token_var.set(token)
        ctx_org = _gateway_org_var.set(org)
        try:
            await self.app(scope, receive, send)
        finally:
            _gateway_token_var.reset(ctx_token)
            _gateway_org_var.reset(ctx_org)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all tools."""
    # DNS-rebinding protection is disabled because the container runs behind
    # mcp-gateway on an internal Docker network and is never publicly exposed.
    mcp = FastMCP(
        name="github-org-mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
        json_response=True,
    )

    def client_factory() -> GitHubClient | None:
        return get_client_from_context(settings)

    if not settings.has_credentials:
        # Graceful degradation: register only a diagnostic tool when no credentials are available.
        @mcp.tool()
        async def github_test_connection() -> str:
            """Test GitHub API connection. Shows configuration requirements when unconfigured."""
            return (
                "Error: Missing GitHub credentials.\n\n"
                "Set the required environment variables (env mode):\n"
                "  GITHUB_TOKEN=your_oauth_access_token\n"
                "  GITHUB_ORG=your_org_slug\n\n"
                "Or use gateway mode (per-request credentials):\n"
                f"  AUTH_MODE=gateway\n"
                f"  Send headers: {settings.github_token_header}: <token>, "
                f"{settings.github_org_header}: <org>"
            )

        print(
            "Warning: No GitHub credentials found. Only the diagnostic tool is available.",
            file=sys.stderr,
        )
        return mcp

    # Register all tool modules here.
    from .tools import members

    members.register(mcp, client_factory)

    return mcp
