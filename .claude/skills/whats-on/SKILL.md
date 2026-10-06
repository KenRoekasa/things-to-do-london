---
name: whats-on
description: Find out what is actually happening in London on a given date or weekend by searching the resource links already in the guide, then fold the durable finds into the events calendar. Use when asked "what's on this weekend", "what should we do on Saturday", "anything happening on 12 Sep", or when planning a specific day out.
---

# What's on

Two halves, always run in this order: **research the date**, then **write the keepers into
`build/events-2026.main.html` and rebuild**. Reporting without updating the calendar leaves the
work stranded in a chat log.

## 1. Pin the dates down

Convert whatever the user said into absolute dates *with weekdays* — "this Saturday" is a trap
when the session has been running across midnight. State them back in the answer.

Then check them against the weekday before trusting any listing. Aggregators and venue pages
routinely say "Saturday 23rd" when the 23rd is a Sunday — Secret London and the Battersea Power
Station events page both did it in the same week. **The numeric date is the reliable half; the
weekday label is not.** Where they disagree on something load-bearing, report the conflict rather
than picking one, and tell the user to confirm with the venue.

## 2. Fetch the sources

The URLs to search are already in the guide — `## 🌐 Websites & Resources` in
`london-activities.md`. Read that section rather than hardcoding a list, since it grows.

Fetch in parallel batches. Known behaviour as of Aug 2026:

| Source | Works? |
| --- | --- |
| `timeout.com/london/things-to-do-in-london-this-weekend` | **Best single source.** Dense, dated, categorised. Start here |
| `secretldn.com/things-to-do-london-weekend/` | Works — good on pop-ups and one-off bar events. `.../things-to-do-in-london-weekend/` is the same page and works too |
| Venue programme pages (Battersea Power Station, King's Cross, etc.) | Work, and are the **only** trustworthy source for prices and times |
| `timeout.com/london` (homepage) | Thin — only ongoing theatre. Use the weekend URL above |
| `londonist.com`, `visitlondon.com` | 403 Forbidden |
| `skiddle.com`, `designmynight.com`, `concreteplayground.com` | Listings load via JS date filters; a plain fetch returns an empty shell |

Beyond the resource list, fetch the programme page of any venue the day is being built around,
plus the specific event page when a date range hides a per-day line-up — e.g. Summer Sounds runs
eleven days but has exactly one Saturday slot, which only the event page reveals.

## 3. Verify before repeating

- **Prices, times and closing dates come from the venue, never the aggregator.** Time Out
  described Electric Summer as free roller skating when the operator's ticket page has the rink at
  £12; it put Big Penny Beach Club's last day a week late; Secret London had Timewalk ending in
  August at £31.50 when the venue says 30 September from £28.50. Every one of these was wrong in
  the direction that changes the plan. Follow the "Book Now" link to the ticketing domain if the
  venue page is vague, and web-search the event name to find the official domain rather than
  guessing a URL.
- Free entry with paid attractions is common — say which is which, it changes the day's budget.
- If an aggregator pairs an exhibition with a venue that looks wrong (wrong gallery, wrong
  postcode), **drop the entry** rather than pass on a bad address.
- Flag what is in its final weekend. "Ends Sunday" is the most decision-useful fact you can give.

## 4. Report

Lead with anything on at the venue the user already picked, then group the rest:
ending-this-weekend / ticketed / free. Name the sources that failed so the gaps are visible and
the user can check those themselves.

## 5. Fold the keepers into the calendar

**This is not optional and not a follow-up question.** Add every durable find to
`build/events-2026.main.html`.

Add it if it is dated and would still be worth knowing next time: multi-week runs, annual
festivals, seasonal pop-ups, exhibitions with a closing date. Skip single-night club nights,
one-off restaurant takeovers and anything already in the file.

Card format, inside the right `<section class="month-group">`:

```html
<div class="event-card">
  <span class="event-date">Sat 12</span>
  <div class="event-body">
    <h3><a href="URL" target="_blank" rel="noopener">Name<span aria-hidden="true">&#8599;</span></a></h3>
    <p>Where &mdash; what it is.</p>
  </div>
</div>
```

Ranges read `Thu 13 &ndash; Sun 23`; ranges crossing a month read `Wed 29 Jul &ndash; Mon 31` and
live in the month they end. Use `&mdash;`, `&ndash;`, `&amp;` and `&#x27;` — the file is entity-escaped
throughout. Link to the venue's own page, not the aggregator you found it on.

Two things that break silently:

- Adding the **first** event to a month means deleting that month's `<div class="month-empty">…</div>`,
  or the build leaves the month's filter pill disabled and the event unreachable.
- Update the `<span class="count">` in the month head by hand. `app.js` recalculates it on load,
  but it must read right before JS runs.

A venue worth returning to — as opposed to a dated event — belongs in `london-activities.md`
instead, under the matching `##` section. Both can be true; put it in both.

## 6. Rebuild, always

```sh
python3 build.py
```

The local build is a check — it fails loudly on a malformed entry, and the output can be opened
to eyeball the result. The generated HTML is not committed: commit the source edit and the
`Build and deploy` workflow rebuilds and publishes on push. Run the build twice and compare
checksums (`md5sum *.html`) — a second-run difference means something non-deterministic crept in.
