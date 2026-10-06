# inbox-state

Working memory for `tools/inbox.py`, written by the *Inbox and health check*
workflow on `main`. Not part of the site; safe to ignore.

- `seen.json` — every post already judged (URL → publish date), forgotten after 60 days
- `queue.json` — finds waiting for the next weekly inbox
