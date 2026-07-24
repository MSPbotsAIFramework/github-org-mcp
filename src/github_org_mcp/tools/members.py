"""GitHub organization member-management tools.

Tool naming convention: <vendor>_<action>_<resource> (vendor prefix: github).
All tools operate on the org resolved from the current request context
(the X-GitHub-Org header in gateway mode).
"""

import json
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..api_client import GitHubClient, GitHubError

_NO_CREDENTIALS = (
    "Error: No GitHub credentials configured. In gateway mode send the "
    "X-GitHub-Token and X-GitHub-Org headers; in env mode set GITHUB_TOKEN and GITHUB_ORG."
)


def register(mcp: FastMCP, client_factory: Callable[[], GitHubClient | None]) -> None:
    @mcp.tool()
    async def github_list_org_members(
        role: str = "all",
        filter: str = "all",
        per_page: int = 30,
        page: int = 1,
    ) -> str:
        """List members of the GitHub organization.

        Args:
            role: Filter by member role — "all", "admin", or "member" (default: "all").
            filter: Filter members — "all" or "2fa_disabled" (default: "all").
            per_page: Results per page, max 100 (default: 30).
            page: Page number of the results to fetch (default: 1).
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            result = await client.get(
                f"/orgs/{client.org}/members",
                params={"role": role, "filter": filter, "per_page": per_page, "page": page},
            )
            return json.dumps(result, indent=2)
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_get_org_membership(username: str) -> str:
        """Get a user's membership (role and state) in the organization.

        Args:
            username: The GitHub handle of the user to look up.
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            result = await client.get(f"/orgs/{client.org}/memberships/{username}")
            return json.dumps(result, indent=2)
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_set_org_membership(username: str, role: str = "member") -> str:
        """Add a user to the organization or update their role.

        If the user is not yet a member, GitHub sends an invitation (state "pending");
        if they already are a member, their role is updated.

        Args:
            username: The GitHub handle of the user to add or update.
            role: Role to assign — "member" or "admin" (default: "member").
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            result = await client.put(
                f"/orgs/{client.org}/memberships/{username}",
                {"role": role},
            )
            return json.dumps(result, indent=2)
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_remove_org_member(username: str) -> str:
        """Remove a user from the organization.

        Removing a member also removes them from all teams and revokes their
        access to organization repositories.

        Args:
            username: The GitHub handle of the user to remove.
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            await client.delete(f"/orgs/{client.org}/members/{username}")
            return f"Member '{username}' removed from organization '{client.org}'."
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_list_org_invitations(per_page: int = 30, page: int = 1) -> str:
        """List the organization's pending member invitations.

        Args:
            per_page: Results per page, max 100 (default: 30).
            page: Page number of the results to fetch (default: 1).
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            result = await client.get(
                f"/orgs/{client.org}/invitations",
                params={"per_page": per_page, "page": page},
            )
            return json.dumps(result, indent=2)
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_create_org_invitation(
        invitee_id: int | None = None,
        email: str | None = None,
        role: str = "direct_member",
        team_ids: list[int] | None = None,
    ) -> str:
        """Invite a user to the organization by GitHub user ID or by email.

        Exactly one of invitee_id or email must be provided.

        Args:
            invitee_id: GitHub numeric user ID of the person to invite.
            email: Email address of the person to invite (for users without a known ID).
            role: Invitee role — "direct_member", "admin", or "billing_manager"
                (default: "direct_member").
            team_ids: Optional list of team IDs to add the invitee to.
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        if (invitee_id is None) == (email is None):
            return "Error: provide exactly one of 'invitee_id' or 'email'."
        body: dict = {"role": role}
        if invitee_id is not None:
            body["invitee_id"] = invitee_id
        if email is not None:
            body["email"] = email
        if team_ids is not None:
            body["team_ids"] = team_ids
        try:
            result = await client.post(f"/orgs/{client.org}/invitations", body)
            return json.dumps(result, indent=2)
        except GitHubError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def github_cancel_org_invitation(invitation_id: int) -> str:
        """Cancel a pending organization invitation.

        Args:
            invitation_id: The numeric ID of the invitation to cancel
                (from github_list_org_invitations).
        """
        client = client_factory()
        if client is None:
            return _NO_CREDENTIALS
        try:
            await client.delete(f"/orgs/{client.org}/invitations/{invitation_id}")
            return f"Invitation {invitation_id} cancelled for organization '{client.org}'."
        except GitHubError as e:
            return f"Error: {e}"
