# Service Overview

This repository powers a small Telegram marketplace.  Each Python script in
`src/` acts as a stand‑alone service invoked from the Makefile.  See
[`setup.md`](setup.md) for installation instructions.

## tg_client.py
Uses Telethon to mirror the target chats as a normal user account.  On start it
ensures every entry in `CHATS` is joined so private channels are accessible.
It then fetches all messages newer than the last saved ID for each chat before
listening for real‑time updates.  Incoming messages are stored as Markdown under
`data/raw/<chat>/<year>/<month>/<id>.md` with basic metadata at the top.  Media
files are placed next to a `.md` description under
`data/media/<chat>/<year>/<month>/` using their SHA‑256 hash plus extension.
Nothing is deleted; edits simply overwrite the Markdown.

## caption.py
Calls GPT‑4o Vision to caption the images in `data/media`.  The result is stored
under `data/media_desc/<sha>.md`.  Captions are later included in the lot
chopper prompt.

## chop.py
Feeds the message text plus any media captions to GPT‑4o to extract individual
lots.  Output is a JSON file per message in `data/lots` ready for further
processing.

## embed.py
Generates `text-embedding-4o` vectors for each lot.  Vectors are stored both in
`data/vectors.jsonl` and in the `lot_vec` table using pgvector.

Translations are now produced by `chop.py` itself.  Fields like
`title_ru` or `description_ka` are included in the lot JSON directly.

## build_site.py
Uses Jinja templates from the `templates/` directory to render the static HTML
version of the marketplace into `data/views`.  The resulting files can be served
as is.

## alert_bot.py
Simple Telegram bot that lets users subscribe to notifications.  Alerts are sent
to all subscribers when new lots are detected.

## Makefile
The `Makefile` in the repository root wires these scripts together.  Running
`make update` performs a full refresh: pulling messages, captioning images,
chopping, embedding and rebuilding the static site.
