# Service Overview

This repository powers a small Telegram marketplace.  Each Python script in
`src/` acts as a stand-alone service invoked from the Makefile.  See
[`setup.md`](setup.md) for installation instructions.

## tg_client.py
Uses Telethon to mirror the target chats as a normal user account.

* **Chat access.** At startup the client checks that the account has already
  joined every chat listed in `CHATS`, joining any missing private channels so
  their history is accessible.
* **Back-fill strategy.** The client keeps only the last month on disk.  When
  fetching history it jumps straight to the cut-off date instead of scrolling
  from the very first message.  If less than 31 days are stored each run
  back-fills **at most one additional day**; once a full month is present only
  newer messages are pulled.
* **Realtime updates.** Once the historical backlog is caught up the client
  switches to listening for live events.
* **Multiple sessions.** The Telegram client runs with ``sequential_updates=True``
  so several sessions can use the same account without missing events.
* **Heartbeat.** A background task logs a ``Heartbeat`` message every minute and
  warns if no updates arrive for more than five minutes.
* **Storage layout.** Incoming messages are saved as Markdown under
  `data/raw/<chat>/<year>/<month>/<id>.md` with basic metadata at the top.
  Media files live beside a `.md` description in
  `data/media/<chat>/<year>/<month>/`, named by their SHA-256 hash plus
  extension.  Albums are merged into a single file so every attachment appears
  together.  Nothing is deleted; edits overwrite the Markdown in place.
  Attachments that fail to download are skipped with a warning.

Metadata fields include at least:

- `id`, `chat`, `date`, `reply_to`, `is_admin`
- `sender` (numeric), `sender_name`, `sender_username`, `sender_phone`,
  `tg_link`
- `group_id` if part of an album
- `files` – list of stored media paths

## caption.py
Calls GPT-4o Vision to caption the images in `data/media`.  The result is stored
under `data/media_desc/<sha>.md`.  Captions are later included in the lot
chopper prompt.

## chop.py
Feeds the message text plus any media captions to GPT-4o to extract individual
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
