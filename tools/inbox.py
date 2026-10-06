#!/usr/bin/env python3
"""Discovery inbox: collect London things-to-do articles daily, post them weekly.

    python3 tools/inbox.py collect --state DIR     # daily: read the feeds, queue new finds
    python3 tools/inbox.py post --state DIR        # weekly: open the inbox issue, clear the queue
    python3 tools/inbox.py preview                 # what would be queued right now (no state)

Nothing is published to the site. Finds land in a GitHub issue for a human to
read; the useful ones get added to the guide by hand, with dates checked
against the organiser. State (what's been seen, what's queued) lives in DIR,
which the workflow keeps on the `inbox-state` branch.

Only article titles and links are kept and posted, never article text: the
issue is a reading list pointing back at the publishers.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "inbox"
UA = "london-guide-inbox/1.0 (+https://github.com/KenRoekasa/things-to-do-london)"

# Feeds hold only their latest 10–20 posts, which for the busier sites is less
# than a day — hence collecting daily and reading a few pages back.
FEEDS = {
    "Londonist": ["https://londonist.com/feed", "https://londonist.com/feed?page=2"],
    "Secret London": [f"https://secretldn.com/feed/?paged={n}" for n in (1, 2, 3)],
    "IanVisits": [f"https://www.ianvisits.co.uk/feed/?paged={n}" for n in (1, 2, 3)],
}

MAX_AGE = timedelta(days=10)   # ignore older posts entirely
FORGET_AFTER = timedelta(days=60)

# A post is kept if its title or tags hit KEEP, unless anything hits DROP.
# Tune these as the inbox shows what slips through or gets wrongly cut.
KEEP = [
    "things to do", "weekend", "exhibition", "opening", "opens", "now open",
    "new bar", "new restaurant", "pop-up", "pop up", "festival", "immersive",
    "market", "christmas", "halloween", "pumpkin", "fireworks", "light trail",
    "ice rink", "skating", "arcade", "rooftop", "ticket alert", "free entry",
    "free to visit", "food & drink", "theatre & arts", "london exhibitions",
    "museums & galleries",
]
DROP = [
    "gig", "concert", "uk tour", "world tour", "tour dates", "album",
    "headline set", "line-up", "lineup",
    "transport news", "general news", "obituary", "dies", "court",
    "music", "sponsored", "supermarket", "branch",
]


@dataclass
class Find:
    title: str
    url: str
    source: str
    published: str          # ISO 8601
    tags: list[str] = field(default_factory=list)


# --- fetching ----------------------------------------------------------------

def clean_url(url: str) -> str:
    """Drop tracking parameters so the same post doesn't look new twice."""
    parts = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query)
             if not k.startswith("utm_")]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query), fragment=""))


def read_feed(source: str, url: str) -> list[Find]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    finds = []
    for item in root.iter("item"):
        title = html.unescape(item.findtext("title", "")).strip()
        link = item.findtext("link", "").strip()
        pub = item.findtext("pubDate")
        if not (title and link and pub):
            continue
        finds.append(Find(
            title=title,
            url=clean_url(link),
            source=source,
            published=parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(),
            tags=[html.unescape(c.text or "").strip() for c in item.findall("category")],
        ))
    return finds


def fetch_all() -> list[Find]:
    finds = []
    for source, urls in FEEDS.items():
        for url in urls:
            try:
                finds.extend(read_feed(source, url))
            except Exception as e:  # one broken feed shouldn't sink the rest
                print(f"warning: {source} {url}: {e}", file=sys.stderr)
    return finds


# --- filtering ---------------------------------------------------------------

def known_urls() -> set[str]:
    """Every link already in the guide or calendar."""
    text = (ROOT / "london-activities.md").read_text(encoding="utf-8")
    for path in (ROOT / "build").glob("events-*.main.html"):
        text += path.read_text(encoding="utf-8")
    return {clean_url(html.unescape(u)) for u in re.findall(r'https?://[^\s)"<]+', text)}


def hits(words: list[str], text: str) -> bool:
    """Whole-word match, allowing a plural: "exhibition" finds "exhibitions"."""
    return any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", text) for w in words)


def interesting(f: Find) -> bool:
    text = (f.title + " | " + " | ".join(f.tags)).lower()
    return hits(KEEP, text) and not hits(DROP, text)


def fresh(finds: list[Find], skip: set[str], now: datetime) -> list[Find]:
    out, seen_now = [], set()
    for f in finds:
        if f.url in skip or f.url in seen_now:
            continue
        seen_now.add(f.url)
        if now - datetime.fromisoformat(f.published) <= MAX_AGE:
            out.append(f)
    return out


# --- state -------------------------------------------------------------------

def load(state: Path) -> tuple[dict[str, str], list[Find]]:
    seen_path, queue_path = state / "seen.json", state / "queue.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    queue = [Find(**f) for f in json.loads(queue_path.read_text())] if queue_path.exists() else []
    return seen, queue


def save(state: Path, seen: dict[str, str], queue: list[Find]) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "seen.json").write_text(json.dumps(dict(sorted(seen.items())), indent=1) + "\n")
    (state / "queue.json").write_text(json.dumps([asdict(f) for f in queue], indent=1) + "\n")


# --- commands ----------------------------------------------------------------

def collect(state: Path) -> None:
    now = datetime.now(timezone.utc)
    seen, queue = load(state)
    new = fresh(fetch_all(), set(seen) | known_urls(), now)
    kept = [f for f in new if interesting(f)]
    for f in new:                       # remember rejects too, so they aren't re-judged
        seen[f.url] = f.published
    cutoff = now - FORGET_AFTER
    seen = {u: d for u, d in seen.items() if datetime.fromisoformat(d) >= cutoff}
    save(state, seen, queue + kept)
    print(f"collected {len(new)} new posts, queued {len(kept)} (queue now {len(queue) + len(kept)})")


def render(queue: list[Find], now: datetime) -> str:
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    head = f"@{owner} — " if owner else ""
    lines = [
        f"{head}{len(queue)} things-to-do posts from the past week, filtered and minus "
        "anything already in the guide.",
        "",
        "Tick what's worth adding; send it over to have dates checked against the "
        "organiser before it goes in. Close the issue when you're done.",
        "",
    ]
    for source in FEEDS:
        items = sorted((f for f in queue if f.source == source),
                       key=lambda f: f.published, reverse=True)
        if not items:
            continue
        lines.append(f"### {source} ({len(items)})\n")
        for f in items:
            day = datetime.fromisoformat(f.published).strftime("%a %d %b")
            lines.append(f"- [ ] [{f.title}]({f.url}) — {day}")
        lines.append("")
    return "\n".join(lines)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def post(state: Path, dry_run: bool) -> None:
    now = datetime.now(timezone.utc)
    seen, queue = load(state)
    title = f"📥 Inbox — w/c {now:%d %b} ({len(queue)} new)"
    if not queue:
        print("queue empty, nothing to post")
        return
    body = render(queue, now)
    if dry_run:
        print(title, body, sep="\n\n")
        return
    gh("label", "create", LABEL, "--color", "0e8a16", "--force",
       "--description", "Weekly discovery inbox")
    print(gh("issue", "create", "--title", title, "--label", LABEL, "--body", body))
    save(state, seen, [])


def preview() -> None:
    now = datetime.now(timezone.utc)
    new = fresh(fetch_all(), known_urls(), now)
    kept = [f for f in new if interesting(f)]
    print(f"{len(new)} recent posts, {len(kept)} kept\n")
    for f in new:
        mark = "KEEP" if f in kept else "    "
        print(f"{mark}  [{f.source}] {f.title}  {f.tags[:4]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["collect", "post", "preview"])
    ap.add_argument("--state", type=Path, default=ROOT / "inbox-state")
    ap.add_argument("--dry-run", action="store_true", help="post: print instead of posting")
    args = ap.parse_args()
    if args.command == "collect":
        collect(args.state)
    elif args.command == "post":
        post(args.state, args.dry_run)
    else:
        preview()


if __name__ == "__main__":
    main()
