import os
#!/usr/bin/env python3

import json
import re
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from connectors.youtube import search as youtube_search

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


# AESF RADAR HISTORICO
# Conservamos información capturada durante 48 horas.
HISTORY_HOURS = 48
HISTORY_FILE = OUT / "history.json"


def load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data.get("items", [])

        if isinstance(data, list):
            return data

    except Exception as exc:
        print("AVISO histórico:", exc)

    return []


def item_datetime(item):
    value = item.get("time")

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def keep_recent(items, hours=48):
    limit = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = []

    for item in items:
        dt = item_datetime(item)

        # Si una fuente no proporciona fecha, no la descartamos
        # automáticamente. Se conservará y podremos mejorarla después.
        if dt is None or dt >= limit:
            result.append(item)

    return result


old_history = load_history()

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


# REDES · YouTube
# Se ejecuta únicamente cuando GitHub Actions define RUN_YOUTUBE=1.
# Así evitamos consumir cuota de la API en cada ciclo del recolector.
run_youtube = os.environ.get("RUN_YOUTUBE", "0") == "1"

# Consulta dinámica para AESF RADAR.
# GitHub Actions podrá definir RADAR_QUERY en cada búsqueda.
radar_query = os.environ.get("RADAR_QUERY", "Ferrol").strip() or "Ferrol"

if run_youtube:
    try:
        yt = youtube_search(radar_query, hours=HISTORY_HOURS, max_results=25)
        yt_items = yt.get("items", [])

        status["youtube"] = {
            "ok": yt.get("configured", False) and not yt.get("error"),
            "count": len(yt_items),
            "name": "YouTube",
        }

        if yt.get("error"):
            status["youtube"]["error"] = yt["error"]
            print(f'ERROR YouTube · {radar_query}: {yt["error"]}')
        else:
            print(f'OK  YouTube · {radar_query}: {len(yt_items)}')

        if yt_items:
            with open(OUT / "youtube.json", "w", encoding="utf-8") as f:
                json.dump(yt_items, f, ensure_ascii=False, indent=2)

            all_items.extend(yt_items)

    except Exception as exc:
        status["youtube"] = {
            "ok": False,
            "count": 0,
            "name": "YouTube",
            "error": str(exc),
        }
        print(f'ERROR YouTube: {exc}')
else:
    status["youtube"] = {
        "ok": True,
        "count": 0,
        "name": "YouTube",
        "skipped": True,
    }
    print("SKIP YouTube · reservado para ciclo programado")


# Mezclamos lo recién capturado con el histórico anterior.
history_items = dedupe(old_history + all_items)
history_items = keep_recent(history_items, HISTORY_HOURS)

history_items.sort(
    key=lambda x: x.get("time") or "",
    reverse=True
)

history_payload = {
    "hours": HISTORY_HOURS,
    "count": len(history_items),
    "items": history_items,
}

# history.json solo cambia cuando cambia realmente el contenido.
with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history_payload, f, ensure_ascii=False, indent=2)

payload_core = {
    "count": len(history_items),
    "sources": status,
    "items": history_items,
}

all_path = OUT / "all.json"
generated_at = None

# Si los datos son exactamente iguales, conservamos generated_at.
# Así GitHub no crea un commit cada cinco minutos sin novedades.
if all_path.exists():
    try:
        with open(all_path, "r", encoding="utf-8") as f:
            old_payload = json.load(f)

        old_core = {
            "count": old_payload.get("count"),
            "sources": old_payload.get("sources"),
            "items": old_payload.get("items"),
        }

        if old_core == payload_core:
            generated_at = old_payload.get("generated_at")

    except Exception:
        pass

payload = {
    "generated_at":
        generated_at or datetime.now(timezone.utc).isoformat(),
    **payload_core,
}

with open(all_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print()
print("NUEVOS/ACTUALES:", len(all_items))
print("HISTORICO 48H:", len(history_items))
print("GENERADO: data/history.json + data/all.json")
