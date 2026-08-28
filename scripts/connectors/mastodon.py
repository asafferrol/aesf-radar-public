#!/usr/bin/env python3

import json
import re
import html
import urllib.parse
import urllib.request

INSTANCES = [
    "https://mastodon.social",
    "https://mstdn.social",
    "https://mastodon.online",
]

USER_AGENT = "AESF-RADAR/0.6"


def clean(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def search(query, limit=20):
    results = []
    errors = {}

    for instance in INSTANCES:
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "type": "statuses",
                "limit": limit,
            })

            url = f"{instance}/api/v2/search?{params}"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.load(response)

            for post in data.get("statuses", []):
                account = post.get("account", {})
                content = clean(post.get("content", ""))

                results.append({
                    "title": content[:180] or "Publicación Mastodon",
                    "description": content,
                    "url": post.get("url", ""),
                    "time": post.get("created_at"),
                    "source": "Mastodon",
                    "source_id": "mastodon",
                    "type": "REDES",
                    "network": "mastodon",
                    "author": account.get("acct", ""),
                    "instance": instance,
                })

        except Exception as exc:
            errors[instance] = str(exc)

    unique = {}
    for item in results:
        key = item.get("url") or (
            item.get("author", "") + "|" + item.get("description", "")
        )
        unique[key] = item

    items = list(unique.values())

    items.sort(
        key=lambda x: x.get("time") or "",
        reverse=True,
    )

    return {
        "network": "mastodon",
        "query": query,
        "count": len(items),
        "items": items,
        "errors": errors,
    }


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]).strip() or "Ferrol"

    result = search(query)

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))
