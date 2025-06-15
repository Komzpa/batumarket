# Service Overview

This repository powers a small Telegram marketplace.  Each Python script in
`src/` acts as a stand‑alone service invoked from the Makefile.

## tg_bot.py
Listens to the configured chats and stores every incoming message as Markdown in
`data/raw`.  Media files are downloaded to `data/media` under their SHA‑256
names.  Nothing is deleted; edits simply overwrite the Markdown.

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

## translate.py
Translates the English description of every lot into the languages specified in
`config.LANGS`.  The file is updated in place with extra fields such as
`description_ru`.

## build_site.py
Uses Jinja templates to render the static HTML version of the marketplace into
`data/views`.  The resulting files can be served as is.

## alert_bot.py
Simple Telegram bot that lets users subscribe to notifications.  Alerts are sent
to all subscribers when new lots are detected.

## Makefile
`src/Makefile` wires these scripts together.  Running `make -f src/Makefile
update` performs a full refresh: pulling messages, captioning images, chopping,
embedding, translating and rebuilding the static site.
