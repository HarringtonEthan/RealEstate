"""Reddit source adapter.

Uses Reddit's public JSON endpoints at very low volume with a descriptive
User-Agent. For sustained daily use, register a script app (reddit.com/prefs/apps)
and switch to the official OAuth API — this adapter keeps volume well under
public limits (one request per subreddit per run, generous delays).

We collect only public posts, store the link + public text, and never
republish datasets.
"""

import time
from datetime import datetime, timezone

import httpx

from .. import config


def fetch_new_posts() -> list[dict]:
    """Fetch recent posts from the configured subreddits. Returns normalized items."""
    items = []
    headers = {"User-Agent": config.REDDIT_USER_AGENT}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        for sub in config.REDDIT_SUBREDDITS:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit={config.REDDIT_LIMIT_PER_SUB}"
            try:
                resp = client.get(url)
                if resp.status_code == 429:
                    time.sleep(10)
                    resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:  # network/blocked/etc — skip sub, keep going
                items.append({"_error": f"r/{sub}: {exc}"})
                continue
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
            time.sleep(2)  # be polite between subreddits
    return items
