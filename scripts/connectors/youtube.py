#!/usr/bin/env python3

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.googleapis.com/youtube/v3/search"


def search(query, hours=48, max_results=25):
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()

    if not key:
        return {
            "network": "youtube",
            "query": query,
            "configured": False,
            "count": 0,
            "items": [],
            "error": "YOUTUBE_API_KEY no configurada en este entorno",
        }

    after = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "order": "date",
        "publishedAfter": after,
        "maxResults": min(max_results, 50),
        "key": key,
    }

    url = API + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AESF-RADAR/0.6",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as exc:
        return {
            "network": "youtube",
            "query": query,
            "configured": True,
            "count": 0,
            "items": [],
            "error": str(exc),
        }

    items = []

    for row in data.get("items", []):
        video_id = row.get("id", {}).get("videoId")
        snippet = row.get("snippet", {})

        if not video_id:
            continue

        items.append({
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "time": snippet.get("publishedAt"),
            "source": "YouTube",
            "source_id": "youtube",
            "type": "REDES",
            "network": "youtube",
            "author": snippet.get("channelTitle", ""),
        })

    return {
        "network": "youtube",
        "query": query,
        "configured": True,
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "Ferrol"
    print(json.dumps(search(query), ensure_ascii=False, indent=2))
