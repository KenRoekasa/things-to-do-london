#!/usr/bin/env python3
"""Live query API over the London Field Guide.

    python3 tools/api_server.py                       # serve on :8000 from the published site
    python3 tools/api_server.py --port 8080
    python3 tools/api_server.py --data api            # serve a local build instead

The static JSON that build.py publishes (api/guide.json, api/events-YYYY.json)
stays the single source of data: this server only reads it — from the live
GitHub Pages site by default, refreshed every few minutes — and answers
questions the static files can't, like "what's on this Saturday?".

    GET /                          what's here
    GET /events                    every event; filter with any of:
          ?date=2026-10-24           on that day
          ?from=2026-10-24&to=2026-10-31   overlapping that range
          ?month=10                  in that month (dated, or undated and filed there)
          ?q=rum                     text search over name, date label and description
          ?upcoming=1                from today on
          ?limit=20
    GET /weekend[?date=…]          this weekend (or the weekend on/after date): Sat + Sun
    GET /today                     what's on today
    GET /guide?q=rooftop&category=Bars & Dining
    GET /search?q=pumpkin          events and guide entries together
    GET /health

Every response is JSON with CORS open, so a page, a shortcut or a bot can call
it. Stdlib only, Python 3.11+, like the build.

Running it on a server: copy this one file over (nothing else is needed — it
reads the published site), then keep it up with systemd, e.g.

    # /etc/systemd/system/london-api.service
    [Service]
    ExecStart=/usr/bin/python3 /opt/london-api/api_server.py --host 127.0.0.1 --port 8000
    Restart=always
    [Install]
    WantedBy=multi-user.target

and put it behind the existing web server (nginx: `location /api/ { proxy_pass
http://127.0.0.1:8000/; }`). Content changes need no redeploy: a push rebuilds
the site and the server picks up the new JSON within REFRESH seconds.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SITE = "https://kenroekasa.github.io/things-to-do-london/"
REFRESH = 300  # seconds between re-reads of the published JSON
UA = "london-field-guide-api/1.0"
OPEN_ENDED = timedelta(days=90)  # how long an "Opens …" with no stated end counts as on


class Data:
    """The guide and every events year, re-read every REFRESH seconds."""

    def __init__(self, source: str):
        self.source = source  # a URL ending in / or a local api/ directory
        self.lock = threading.Lock()
        self.loaded_at = 0.0
        self.guide: dict = {"count": 0, "categories": []}
        self.events: list[dict] = []
        self.years: list[int] = []
        self.error = ""

    def _read(self, name: str) -> dict:
        if self.source.startswith(("http://", "https://")):
            req = urllib.request.Request(f"{self.source}api/{name}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        return json.loads((Path(self.source) / name).read_text(encoding="utf-8"))

    def refresh(self, force: bool = False) -> None:
        with self.lock:
            if not force and time.time() - self.loaded_at < REFRESH:
                return
            try:
                index = self._read("index.json")
                guide = self._read("guide.json")
                events, years = [], []
                for key, meta in index["endpoints"].items():
                    if key.startswith("events-"):
                        data = self._read(meta["path"].split("/")[-1])
                        years.append(data["year"])
                        events.extend(dict(e, year=data["year"]) for e in data["events"])
                self.guide, self.events, self.years = guide, events, sorted(years)
                self.loaded_at, self.error = time.time(), ""
            except Exception as e:  # keep serving the last good copy
                self.error = f"{type(e).__name__}: {e}"
                if not self.loaded_at:
                    raise


# --- queries -------------------------------------------------------------------

def d(iso: str | None) -> date | None:
    return date.fromisoformat(iso) if iso else None


def on_day(ev: dict, day: date) -> bool:
    if not ev["dated"]:
        return False
    if ev.get("days"):
        return day.isoformat() in ev["days"]
    start, end = d(ev["start"]), d(ev["end"])
    if end is None:  # an opening with no stated close: assume a season-long run
        end = start + OPEN_ENDED
    return start <= day <= end


def overlaps(ev: dict, lo: date, hi: date) -> bool:
    if not ev["dated"]:
        return False
    if ev.get("days"):
        return any(lo <= d(x) <= hi for x in ev["days"])
    start, end = d(ev["start"]), d(ev["end"])
    if end is None:
        end = start + OPEN_ENDED
    return start <= hi and end >= lo


def in_month(ev: dict, month: int, year: int) -> bool:
    if not ev["dated"]:
        return ev["month"] == month and ev["year"] == year
    lo = date(year, month, 1)
    hi = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
    return overlaps(ev, lo, hi)


def text_hit(needle: str, *fields: str | None) -> bool:
    """Match from the start of a word, so "rum" finds RumFest but not drums."""
    return re.search(r"\b" + re.escape(needle), " ".join(f or "" for f in fields).lower()) is not None


def sort_key(ev: dict):
    return (not ev["dated"], ev.get("start") or f"{ev['year']}-{ev['month']:02d}-99", ev["name"])


def weekend_of(day: date) -> tuple[date, date]:
    """The Sat–Sun on or after `day` (today if it's already the weekend)."""
    if day.weekday() == 6:
        return day - timedelta(days=1), day
    sat = day + timedelta(days=(5 - day.weekday()) % 7)
    return sat, sat + timedelta(days=1)


# --- http ----------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    data: Data  # set in main()
    server_version = "LondonFieldGuide/1.0"

    def log_message(self, fmt, *args):  # one short line per request
        print(f"{self.address_string()} {fmt % args}")

    def send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        route = url.path.rstrip("/") or "/"
        try:
            self.data.refresh()
            handler = ROUTES.get(route)
            if not handler:
                return self.send(404, {"error": f"no such endpoint: {route}", "see": "/"})
            self.send(200, handler(self.data, q))
        except ValueError as e:  # bad dates, months, limits
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(503, {"error": f"data unavailable: {e}"})


def today() -> date:
    return date.today()


def r_index(data: Data, q: dict) -> dict:
    return {
        "name": "London Field Guide — live API",
        "source": data.source,
        "years": data.years,
        "events": len(data.events),
        "guide_entries": data.guide["count"],
        "endpoints": {
            "/events": "date=YYYY-MM-DD | from=…&to=… | month=1-12 [&year=] | q=text | upcoming=1 | limit=N",
            "/weekend": "date=YYYY-MM-DD (optional)",
            "/today": "",
            "/guide": "q=text | category=name",
            "/search": "q=text",
            "/health": "",
        },
    }


def r_events(data: Data, q: dict) -> dict:
    found = list(data.events)
    query = {}
    if "date" in q:
        day = date.fromisoformat(q["date"]); query["date"] = day.isoformat()
        found = [e for e in found if on_day(e, day)]
    if "from" in q or "to" in q:
        lo = date.fromisoformat(q.get("from") or q["to"])
        hi = date.fromisoformat(q.get("to") or q["from"])
        if hi < lo:
            raise ValueError("'to' is before 'from'")
        query.update({"from": lo.isoformat(), "to": hi.isoformat()})
        found = [e for e in found if overlaps(e, lo, hi)]
    if "month" in q:
        month = int(q["month"])
        if not 1 <= month <= 12:
            raise ValueError("month must be 1-12")
        year = int(q.get("year") or (data.years[0] if len(data.years) == 1 else today().year))
        query.update({"month": month, "year": year})
        found = [e for e in found if in_month(e, month, year)]
    if q.get("upcoming") in ("1", "true", "yes"):
        query["upcoming"] = True
        t = today()
        found = [e for e in found if not e["dated"] or overlaps(e, t, date(t.year + 5, 1, 1))]
    if q.get("q"):
        needle = q["q"].strip().lower(); query["q"] = needle
        found = [e for e in found if text_hit(needle, e["name"], e["when"], e["description"])]
    found.sort(key=sort_key)
    total = len(found)
    if "limit" in q:
        found = found[:max(0, int(q["limit"]))]
    return {"query": query, "count": total, "events": found}


def r_weekend(data: Data, q: dict) -> dict:
    sat, sun = weekend_of(date.fromisoformat(q["date"]) if "date" in q else today())
    def day(dd):
        hits = sorted((e for e in data.events if on_day(e, dd)), key=sort_key)
        return {"date": dd.isoformat(), "count": len(hits), "events": hits}
    return {"weekend": f"{sat.isoformat()}/{sun.isoformat()}", "saturday": day(sat), "sunday": day(sun)}


def r_today(data: Data, q: dict) -> dict:
    return r_events(data, {"date": today().isoformat()})


def r_guide(data: Data, q: dict) -> dict:
    needle = (q.get("q") or "").strip().lower()
    cat = (q.get("category") or "").strip().lower()
    out = []
    for c in data.guide["categories"]:
        if cat and cat not in (c["name"].lower(), c["short"].lower()):
            continue
        for e in c["entries"]:
            if not needle or text_hit(needle, e["name"], e["group"], e["note"]):
                out.append(dict(e, category=c["short"]))
    return {"query": {k: v for k, v in (("q", needle), ("category", cat)) if v},
            "count": len(out), "entries": out}


def r_search(data: Data, q: dict) -> dict:
    if not q.get("q"):
        raise ValueError("search needs ?q=")
    ev = r_events(data, {"q": q["q"]})
    gd = r_guide(data, {"q": q["q"]})
    return {"query": {"q": q["q"].strip().lower()}, "events": ev["events"], "guide": gd["entries"],
            "count": ev["count"] + gd["count"]}


def r_health(data: Data, q: dict) -> dict:
    return {"ok": not data.error, "loaded": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data.loaded_at)),
            "events": len(data.events), "guide_entries": data.guide["count"], "last_error": data.error or None}


ROUTES = {"/": r_index, "/events": r_events, "/weekend": r_weekend, "/today": r_today,
          "/guide": r_guide, "/search": r_search, "/health": r_health}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data", default=SITE,
                    help="published site URL (default) or a local api/ directory")
    args = ap.parse_args()

    source = args.data if args.data.startswith("http") else str(Path(args.data).resolve())
    if source.startswith("http") and not source.endswith("/"):
        source += "/"
    Handler.data = Data(source)
    Handler.data.refresh(force=True)
    print(f"serving {len(Handler.data.events)} events and {Handler.data.guide['count']} guide "
          f"entries from {source} on http://{args.host}:{args.port}/")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
