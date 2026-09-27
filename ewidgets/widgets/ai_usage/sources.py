"""Reads how much of their plan limits Claude Code and Codex have used.

Both use the same undocumented endpoints their official CLIs call, signed in
with the OAuth login the CLI saved (~/.claude/.credentials.json,
~/.codex/auth.json). The logins are only read, never refreshed: refreshing
rotates the token the CLI itself uses. When a token has expired, running the
CLI once refreshes it. Everything here blocks, so it runs on a worker thread.

The endpoints, headers and response fields follow ai-usagebar (the Omarchy
plugin), https://github.com/akitaonrails/ai-usagebar. When an endpoint
changes, look there for the fix: src/anthropic/fetch.rs and types.rs for
Claude, src/openai/fetch.rs and types.rs for Codex, and
docs/vendor-endpoints.md.
"""

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from gi.repository import GLib

HTTP_TIMEOUT_S = 10
CACHE_DIR = Path(GLib.get_user_cache_dir()) / "ewidgets"

CLAUDE_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_HEADERS = {
    "anthropic-beta": "oauth-2025-04-20",
    # The endpoint rate-limits hard without a Claude Code user agent.
    "User-Agent": "claude-cli/2.1.281 (external, cli)",
    "Content-Type": "application/json",
}

CODEX_CREDENTIALS = Path.home() / ".codex" / "auth.json"
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HEADERS = {"User-Agent": "codex-cli"}

FIVE_HOURS_S = 5 * 3600
WEEK_S = 7 * 24 * 3600


class SignInNeeded(Exception):
    """The CLI isn't signed in, or its token has expired. The message says what to do."""


@dataclass
class Limit:
    name: str
    percent: float
    resets_at: float | None  # Unix time
    model: str | None = None  # set when the limit covers only this model


@dataclass
class Usage:
    plan: str | None
    limits: list[Limit]
    fetched_at: float


def _get_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.load(response)


def _authorized_get(url: str, headers: dict[str, str], sign_in: str) -> Any:
    try:
        return _get_json(url, headers)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SignInNeeded(sign_in) from e
        raise


def _read_json(path: Path, sign_in: str) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise SignInNeeded(sign_in) from e


def _timestamp(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso).timestamp() if iso else None


def fetch_claude() -> Usage:
    sign_in = "Run claude to sign in"
    oauth = _read_json(CLAUDE_CREDENTIALS, sign_in).get("claudeAiOauth") or {}
    if not oauth.get("accessToken"):
        raise SignInNeeded(sign_in)
    if oauth.get("expiresAt", 0) / 1000 < time.time():
        raise SignInNeeded("Run claude to refresh")
    usage = _authorized_get(
        CLAUDE_USAGE_URL, {**CLAUDE_HEADERS, "Authorization": f"Bearer {oauth['accessToken']}"}, sign_in
    )

    limits = [
        Limit(name, window["utilization"], _timestamp(window.get("resets_at")))
        for name, key in (("Session", "five_hour"), ("Weekly", "seven_day"))
        if (window := usage.get(key))
    ]
    # Weekly limits for a single model, like Fable's.
    for entry in usage.get("limits") or []:
        model = ((entry.get("scope") or {}).get("model") or {}).get("display_name")
        if entry.get("kind") == "weekly_scoped" and model and entry.get("percent") is not None:
            limits.append(Limit("Weekly", entry["percent"], _timestamp(entry.get("resets_at")), model))

    plan = (oauth.get("subscriptionType") or "").capitalize() or None
    tier = oauth.get("rateLimitTier") or ""
    multiplier = next((m for m in ("20x", "5x") if tier.endswith(m)), None)
    if plan and multiplier:
        plan += f" {multiplier}"
    return Usage(plan, limits, time.time())


def _jwt_expiry(token: str) -> float:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
    except (IndexError, ValueError, KeyError):
        return 0


def _codex_window_name(seconds: int) -> str:
    if seconds == FIVE_HOURS_S:
        return "Session"
    if seconds == WEEK_S:
        return "Weekly"
    hours = round(seconds / 3600)
    return f"{hours // 24} days" if hours >= 48 else f"{hours} hours"


def fetch_codex() -> Usage:
    sign_in = "Run codex login"
    tokens = _read_json(CODEX_CREDENTIALS, sign_in).get("tokens") or {}
    token = tokens.get("access_token")
    if not token:
        raise SignInNeeded(sign_in)
    if _jwt_expiry(token) < time.time():
        raise SignInNeeded("Run codex to refresh")
    headers = {**CODEX_HEADERS, "Authorization": f"Bearer {token}"}
    if tokens.get("account_id"):
        headers["ChatGPT-Account-Id"] = tokens["account_id"]
    usage = _authorized_get(CODEX_USAGE_URL, headers, sign_in)

    # Windows are told apart by their length, not their position: some
    # accounts get only the weekly one, as the primary window.
    rate_limit = usage.get("rate_limit") or {}
    windows = [w for key in ("primary_window", "secondary_window") if (w := rate_limit.get(key))]
    windows.sort(key=lambda w: w["limit_window_seconds"])
    limits = [
        Limit(_codex_window_name(w["limit_window_seconds"]), float(w["used_percent"]), w.get("reset_at"))
        for w in windows
    ]
    plan = (usage.get("plan_type") or "").capitalize() or None
    return Usage(plan, limits, time.time())


def load_cache(name: str) -> Usage | None:
    try:
        data = json.loads((CACHE_DIR / f"{name}-usage.json").read_text())
        return Usage(data["plan"], [Limit(**limit) for limit in data["limits"]], data["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_cache(name: str, usage: Usage) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{name}-usage.json").write_text(json.dumps(asdict(usage)))
    except OSError:
        pass
