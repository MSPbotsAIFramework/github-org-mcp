from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Transport
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"

    # Auth mode:
    # "gateway" — production/SOP-compliant: credentials from HTTP headers per request
    # "env"     — local dev only: shared credentials from env vars (not SOP-compliant)
    auth_mode: Literal["env", "gateway"] = "gateway"

    # GitHub API base URL.
    github_base_url: str = "https://api.github.com"

    # GitHub credentials used in "env" mode only (local dev). Ignored in gateway mode,
    # where every request carries its own token + org via HTTP headers.
    github_token: str | None = None
    github_org: str | None = None

    # Header names used to pass per-request credentials in gateway mode.
    # The client must include BOTH headers on every /mcp request.
    github_token_header: str = "X-GitHub-Token"
    github_org_header: str = "X-GitHub-Org"

    @property
    def has_credentials(self) -> bool:
        """Returns True if the server can serve API calls.

        Gateway mode always returns True — each request carries its own credentials.
        Env mode requires both GITHUB_TOKEN and GITHUB_ORG to be set.
        """
        if self.auth_mode == "gateway":
            return True
        return self.github_token is not None and self.github_org is not None


def get_settings() -> Settings:
    return Settings()
