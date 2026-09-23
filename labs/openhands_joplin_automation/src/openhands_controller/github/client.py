"""Small GitHub REST boundary for issue intake and one status comment."""

import json
import re
import time
from collections.abc import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class GitHubRateLimit(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"GitHub rate limit; retry in {retry_after}s")


class GitHubClient:
    def __init__(self, repo: str, token: str, *, request: Callable | None = None):
        if repo.startswith("https://"):
            parsed = urlsplit(repo)
            if parsed.netloc != "github.com" or parsed.query or parsed.fragment:
                raise ValueError("GH_REPO must name a GitHub repository")
            repo = parsed.path.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("GH_REPO must be OWNER/REPO or its https://github.com URL")
        if repo.casefold() == "laurent22/joplin":
            raise ValueError("upstream Joplin is not a demo destination")
        if not token:
            raise ValueError("GH_TOKEN is required")
        self.repo = repo
        self.token = token
        self.request = request or self._request

    def _request(self, method: str, path: str, body: dict | None = None):
        request = Request(
            "https://api.github.com" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429 or (exc.code == 403 and (
                exc.headers.get("X-RateLimit-Remaining") == "0" or exc.headers.get("Retry-After")
            )):
                delay = exc.headers.get("Retry-After")
                reset = exc.headers.get("X-RateLimit-Reset")
                if delay and delay.isdigit():
                    retry_after = int(delay)
                elif reset and reset.isdigit():
                    retry_after = max(1, int(reset) - int(time.time()))
                else:
                    retry_after = 60
                raise GitHubRateLimit(retry_after) from None
            raise RuntimeError(f"GitHub API {method} {path.split('?')[0]} returned HTTP {exc.code}") from None

    def _pages(self, path: str, query: dict[str, str] | None = None) -> list[dict]:
        results = []
        for page in range(1, 101):
            params = {**(query or {}), "per_page": "100", "page": str(page)}
            batch = self.request("GET", path + "?" + urlencode(params))
            if not isinstance(batch, list):
                raise ValueError("GitHub returned a non-list page")
            results.extend(batch)
            if len(batch) < 100:
                return results
        raise RuntimeError("GitHub pagination limit reached")

    def list_open_issues(self, since: str) -> list[dict]:
        return self._pages(f"/repos/{self.repo}/issues",
                           {"state": "open", "sort": "updated", "direction": "asc", "since": since})

    def authenticated_login(self) -> str:
        return str(self.request("GET", "/user")["login"])

    def list_comments(self, number: int) -> list[dict]:
        return self._pages(f"/repos/{self.repo}/issues/{number}/comments")

    def create_comment(self, number: int, body: str) -> dict:
        return self.request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})

    def edit_comment(self, comment_id: int, body: str) -> dict:
        return self.request("PATCH", f"/repos/{self.repo}/issues/comments/{comment_id}", {"body": body})
