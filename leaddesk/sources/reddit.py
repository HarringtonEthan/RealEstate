"""Reddit source adapter.

Reddit's public www.reddit.com/*.json endpoints now block nearly all
automated requests (a 2023+ policy change, not specific to this tool). The
sanctioned fix is read-only OAuth: register a free "script" app at
https://www.reddit.com/prefs/apps and set REDDIT_CLIENT_ID /
REDDIT_CLIENT_SECRET — no Reddit login is stored or required by the app
itself, just app-level read access under the client_credentials grant.

If those aren't set, this falls back to the public endpoint, which is
increasingly likely to 403.

We collect only public posts, store the link + public text, and never
republish datasets.
"""

import time
from datetime import datetime, timezone

import httpx

from .. import config


def _get_oauth_token(client: httpx.Client) -> str | None:
    """App-only OAuth token (client_credentials grant) — read-only, no user login."""
    if not (config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET):
        return None
    try:
        resp = client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET),
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception:
        return None


def _parse_listing(data: dict, sub: str) -> list[dict]:
    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied") or post.get("over_18"):
            continue
        created = post.get("created_utc")
        items.append({
            "item_key": post.get("name", ""),           # e.g. t3_abc123
            "source": f"reddit:r/{sub}",
            "title": post.get("title", ""),
            "body": (post.get("selftext") or "")[:4000],
            "author": f"u/{post.get('author', '[deleted]')}",
            "url": "https://www.reddit.com" + post.get("permalink", ""),
            "signal_date": datetime.fromtimestamp(created, tz=timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ") if created else None,
        })
    return items


def fetch_new_posts() -> list[dict]:
    """Fetch recent posts from the configured subreddits. Returns normalized items."""
    items = []
    headers = {"User-Agent": config.REDDIT_USER_AGENT}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        token = _get_oauth_token(client)
        using_oauth = token is not None
        if token:
            client.headers["Authorization"] = f"Bearer {token}"

        for sub in config.REDDIT_SUBREDDITS:
            base = "https://oauth.reddit.com" if using_oauth else "https://www.reddit.com"
            suffix = "" if using_oauth else ".json"
            url = f"{base}/r/{sub}/new{suffix}?limit={config.REDDIT_LIMIT_PER_SUB}"
            try:
                resp = client.get(url)
                if resp.status_code == 429:
                    time.sleep(10)
                    resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                hint = "" if using_oauth else " (set REDDIT_CLIENT_ID/SECRET for reliable access)"
                items.append({"_error": f"r/{sub}: {exc}{hint}"})
                continue
            items.extend(_parse_listing(data, sub))
            time.sleep(2)  # be polite between subreddits
    return items
