#!/usr/bin/env python3

import json
import re
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SOURCES = [
    {
        "id": "lavoz_ferrol",
        "name": "La Voz de Galicia · Ferrol",
        "type": "NOTICIAS",
        "url": "https://www.lavozdegalicia.es/ferrol/index.xml",
    },
    {
        "id": "dog",
        "name": "DOG · Xunta de Galicia",
        "type": "OFICIAL",
        "url": "https://www.xunta.gal/diario-oficial-galicia/rss/Sumario_es.rss",
    },
    {
        "id": "boe",
        "name": "BOE",
        "type": "OFICIAL",
        "url": "https://www.boe.es/rss/boe.php",
    },
]

OUT = Path("data")
OUT.mkdir(exist_ok=True)


def clean(value):
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def child_text(item, names):
    for child in list(item):
        tag = child.tag.split("}")[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
    return ""


def parse_date(value):
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def download(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AESF-RADAR/0.3",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_feed(source):
    raw = download(source["url"])
    root = ET.fromstring(raw)

    items = []

    candidates = [
        e for e in root.iter()
        if e.tag.split("}")[-1].lower() in ("item", "entry")
    ]

    for item in candidates:
        title = clean(child_text(item, {"title"}))
        description = clean(
            child_text(item, {"description", "summary", "content"})
        )

        link = child_text(item, {"link"})
        if not link:
            for child in list(item):
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    if link:
                        break

        date_raw = child_text(
            item,
            {"pubdate", "published", "updated", "date"}
        )

        if not title:
            continue

        items.append({
            "title": title,
            "description": description,
            "url": link,
            "time": parse_date(date_raw),
            "source": source["name"],
            "source_id": source["id"],
            "type": source["type"],
        })

    return items


def dedupe(items):
    seen = set()
    result = []

    for item in items:
        key = (
            item.get("url", "").strip().lower()
            or item.get("title", "").strip().lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


all_items = []
status = {}

for source in SOURCES:
    try:
        items = parse_feed(source)
        status[source["id"]] = {
            "ok": True,
            "count": len(items),
            "name": source["name"],
        }

        with open(
            OUT / f'{source["id"]}.json',
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        all_items.extend(items)

        print(f'OK  {source["name"]}: {len(items)}')

    except Exception as exc:
        status[source["id"]] = {
            "ok": False,
            "count": 0,
            "name": source["name"],
            "error": str(exc),
        }
        print(f'ERROR {source["name"]}: {exc}')


all_items = dedupe(all_items)

all_items.sort(
    key=lambda x: x.get("time") or "",
    reverse=True
)

payload = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "count": len(all_items),
    "sources": status,
    "items": all_items,
}

with open(OUT / "all.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print()
print("TOTAL:", len(all_items))
print("GENERADO: data/all.json")
