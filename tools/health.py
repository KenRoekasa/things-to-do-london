#!/usr/bin/env python3
"""Weekly housekeeping for the guide and calendar.

    python3 tools/health.py --dry-run     # print the report
    python3 tools/health.py               # post it as a GitHub issue (needs gh + GH_TOKEN)

Finds the things that go stale on their own: links that have died, calendar
entries still marked TBC as their month arrives, dates we flagged as
unconfirmed, and guide notes like "opening Oct 2026" once that date is past.
Stdlib only, like build.py.
"""

from __future__ import annotations

import argparse
import calendar
import html
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_MD = ROOT / "london-activities.md"
EVENTS_FILES = sorted((ROOT / "build").glob("events-*.main.html"))

LABEL = "site-health"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

# How far ahead a TBC or unconfirmed date starts to matter.
LOOKAHEAD = timedelta(days=28)

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

# Many big sites (Kew, BFI, Historic Royal Palaces…) refuse scripted requests.
# Those answers say nothing about whether the page exists, so they're ignored.
BLOCKED = {401, 403, 405, 406, 429, 451, 999}
DEAD = {404, 410}

UNCONFIRMED = re.compile(
    r"unconfirmed|not yet confirmed|dates as listed|not announced", re.I)

# "opening Oct 2026", "opens Thu 15 Oct", "from Mon 2 Nov", "(switch-on Wed 4 Nov)"
STALE_NOTE = re.compile(
    r"\b(?:opening|opens|coming|launch(?:es|ing)?|from|switch-on)\s+"
    r"(?:(?:mon|tue|wed|thu|fri|sat|sun)\w*\s+)?"
    r"(?:(\d{1,2})\s+)?"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"(?:\s+(\d{4}))?",
    re.I,
)


@dataclass
class Link:
    url: str
    name: str
    where: str


@dataclass
class Card:
    month: int
    year: int
    when: str
    name: str
    text: str


# --- reading the sources -----------------------------------------------------

def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def guide_entries() -> list[tuple[str, str]]:
    """(entry name, rest of its text) for each link in the guide, with the
    note that follows it up to the next link."""
    out = []
    for line in SOURCE_MD.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        parts = re.split(r"(\[[^\]]+\]\([^)]+\))", line)
        for i, part in enumerate(parts):
            m = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                note = parts[i + 1] if i + 1 < len(parts) else ""
                out.append((m.group(1), m.group(1) + note))
    return out


def guide_links() -> list[Link]:
    text = SOURCE_MD.read_text(encoding="utf-8")
    return [Link(url, name, "guide")
            for name, url in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text)]


def calendar_cards() -> list[Card]:
    cards = []
    for path in EVENTS_FILES:
        year = int(re.search(r"events-(\d{4})", path.name).group(1))
        src = path.read_text(encoding="utf-8")
        for sec in re.finditer(r'<section class="month-group" id="m-(\w+)".*?</section>', src, re.S):
            month = MONTHS[sec.group(1)]
            for card in re.finditer(r'<div class="event-card">(.*?)\n      </div>\n', sec.group(0), re.S):
                body = card.group(1)
                when = strip_tags(re.search(r'<span class="event-date">(.*?)</span>', body, re.S).group(1))
                name = strip_tags(re.search(r"<h3>(.*?)</h3>", body, re.S).group(1)).rstrip("↗").strip()
                cards.append(Card(month, year, when, name, strip_tags(body)))
    return cards


def calendar_links() -> list[Link]:
    links = []
    for path in EVENTS_FILES:
        src = path.read_text(encoding="utf-8")
        for card in re.finditer(r'<div class="event-card">(.*?)\n      </div>\n', src, re.S):
            body = card.group(1)
            name = strip_tags(re.search(r"<h3>(.*?)</h3>", body, re.S).group(1)).rstrip("↗").strip()
            for url in re.findall(r'href="(https?://[^"]+)"', body):
                links.append(Link(html.unescape(url), name, "calendar"))
    return links


# --- checks --------------------------------------------------------------------

def fetch_status(url: str) -> str:
    """'ok', 'dead: <why>' or 'unreachable: <why>'."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read(1)
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED:
            return "ok"
        if e.code in DEAD:
            return f"dead: {e.code}"
        return f"unreachable: HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.gaierror):
            return "dead: domain doesn't resolve"
        return f"unreachable: {e.reason}"
    except (TimeoutError, socket.timeout):
        return "unreachable: timed out"
    except Exception as e:  # malformed responses, TLS oddities
        return f"unreachable: {type(e).__name__}"


def check_url(url: str) -> str:
    status = fetch_status(url)
    if status != "ok":
        time.sleep(5)  # one retry, so a blip doesn't get reported
        status = fetch_status(url)
    return status


def check_links(links: list[Link]) -> tuple[list[tuple[Link, str]], list[tuple[Link, str]]]:
    first: dict[str, Link] = {}
    for link in links:
        first.setdefault(link.url, link)
    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = dict(zip(first, pool.map(check_url, first)))
    dead = [(first[u], s[6:]) for u, s in statuses.items() if s.startswith("dead")]
    flaky = [(first[u], s[13:]) for u, s in statuses.items() if s.startswith("unreachable")]
    return dead, flaky


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def tbc_due(cards: list[Card], today: date) -> list[Card]:
    due = []
    for c in cards:
        start, _ = month_bounds(c.year, c.month)
        if "TBC" in c.when and start <= today + LOOKAHEAD:
            due.append(c)
    return due


def unconfirmed_due(cards: list[Card], today: date) -> list[Card]:
    due = []
    for c in cards:
        start, end = month_bounds(c.year, c.month)
        if ("TBC" not in c.when and UNCONFIRMED.search(c.text)
                and start <= today + LOOKAHEAD and end >= today):
            due.append(c)
    return due


def stale_notes(today: date) -> list[tuple[str, str]]:
    """Guide notes pointing at a date that has passed."""
    default_year = max((int(re.search(r"(\d{4})", p.name).group(1)) for p in EVENTS_FILES),
                       default=today.year)
    stale = []
    for name, text in guide_entries():
        for m in STALE_NOTE.finditer(text):
            day, mon, year = m.group(1), m.group(2).lower(), m.group(3)
            y = int(year) if year else default_year
            mo = MONTHS[mon]
            d = int(day) if day else calendar.monthrange(y, mo)[1]
            try:
                when = date(y, mo, d)
            except ValueError:
                continue
            if when < today:
                stale.append((name, m.group(0)))
    return stale


# --- report ------------------------------------------------------------------

def render(today: date, dead, flaky, tbc, unconfirmed, stale) -> str:
    lines = []

    def section(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"### {title}\n")
            lines.extend(f"- [ ] {i}" for i in items)
            lines.append("")

    section(f"🔗 Dead links ({len(dead)})",
            [f"**{l.name}** ({l.where}) — {why}  \n  {l.url}" for l, why in dead])
    section(f"🗓️ TBC dates coming up ({len(tbc)})",
            [f"**{c.name}** — {calendar.month_name[c.month]}, still “{c.when}”" for c in tbc])
    section(f"❓ Unconfirmed dates to re-check ({len(unconfirmed)})",
            [f"**{c.name}** — {c.when} ({calendar.month_name[c.month]})" for c in unconfirmed])
    section(f"✏️ Guide notes that have gone stale ({len(stale)})",
            [f"**{name}** — “{phrase}” has passed" for name, phrase in stale])
    section(f"⚠️ Couldn't reach — may be temporary ({len(flaky)})",
            [f"**{l.name}** ({l.where}) — {why}  \n  {l.url}" for l, why in flaky])

    if not lines:
        return ""
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    head = f"@{owner} — " if owner else ""
    return (f"{head}weekly check of the guide and calendar, {today:%a %d %b %Y}.\n\n"
            "Fix by editing `london-activities.md` or `build/events-*.main.html`; "
            "anything fixed drops off next week.\n\n" + "\n".join(lines))


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def post(title: str, body: str) -> None:
    gh("label", "create", LABEL, "--color", "d93f0b", "--force",
       "--description", "Weekly housekeeping report")
    old = gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number",
             "--jq", ".[].number").split()
    new = None
    if body:
        url = gh("issue", "create", "--title", title, "--label", LABEL, "--body", body)
        new = url.rsplit("/", 1)[-1]
        print(url)
    for n in old:
        note = f"Superseded by #{new}." if new else "All clear this week."
        gh("issue", "close", n, "--comment", note)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print instead of posting")
    ap.add_argument("--no-links", action="store_true", help="skip the (slow) link check")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    cards = calendar_cards()
    dead, flaky = ([], []) if args.no_links else check_links(guide_links() + calendar_links())
    body = render(args.today, dead, flaky, tbc_due(cards, args.today),
                  unconfirmed_due(cards, args.today), stale_notes(args.today))
    title = f"🩺 Site health — w/c {args.today:%d %b}"

    if args.dry_run:
        print(title, "\n", body or "All clear.", sep="")
    else:
        post(title, body)


if __name__ == "__main__":
    main()
