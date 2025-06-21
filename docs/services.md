# Service Overview

This repository powers a small Telegram marketplace.  Each Python script in
`src/` acts as a stand-alone service invoked from the Makefile.  See
[`setup.md`](setup.md) for installation instructions.

## tg_client.py
Uses Telethon to mirror the target chats as a normal user account.

* **Chat access.** At startup the client checks that the account has already
  joined every chat listed in `CHATS`, joining any missing private channels so
  their history is accessible.
* **Back-fill strategy.** The client keeps only the last ``KEEP_DAYS`` days on
  disk.  When fetching history it jumps straight to the cut-off date instead of
  scrolling from the very first message.  If less than ``KEEP_DAYS`` days are
  stored the client now pulls the entire missing range in one go so the history
  catches up immediately.  Once the full threshold is present only newer
  messages are pulled.
* **Realtime updates.** Pass ``--listen`` to `tg_client.py` to keep running after
  the initial sync.  Without this flag the client exits once everything is
  synced so the Makefile can continue.
* **Multiple sessions.** The Telegram client runs with ``sequential_updates=True``
  so several sessions can use the same account without missing events.
* **Heartbeat.** A background task logs a ``Heartbeat`` message every minute and
  warns if no updates arrive for more than five minutes.
* **Parallel fetch.** Set ``DOWNLOAD_WORKERS`` in `config.py` to download several
  messages at once when filling gaps in history.
* **Progress bar.** The client counts pending messages per chat and shows a
  progress bar with an estimated time remaining while downloads are running.
* **Storage layout.** Incoming messages are saved as Markdown under
  `data/raw/<chat>/<year>/<month>/<id>.md` with basic metadata at the top.
  Media files live beside a `.md` description in
  `data/media/<chat>/<year>/<month>/`, named by their SHA-256 hash plus
  extension.  Albums are merged into a single file so every attachment appears
  together.  Messages that disappear from Telegram during the last ``KEEP_DAYS`` days are
  removed from disk while edits overwrite the Markdown in place.
* **Resume state.** The timestamp of the last processed batch is stored under
  `data/state/<chat>.txt` so interrupted runs continue from the same point.
  Progress older than the current `KEEP_DAYS` window is ignored so lowering the
  threshold does not re-fetch deleted history. Attachments that fail to download
  are skipped with a warning.  The client ignores videos (`.mp4`), audio files,
  images larger than ten megabytes and any media attached to messages more than
  two days old.

Metadata fields include at least:

- `id`, `chat`, `date`, `reply_to`, `is_admin`
- `sender` (numeric), `sender_name`, `sender_username`, `sender_phone`,
  `post_author`, `tg_link`
- `source:author:telegram`, `source:author:name` – copied into every lot for
  fallback when contact details are missing
- `group_id` if part of an album
- `files` – list of stored media paths

## caption.py
Calls GPT-4o Vision using the instructions in
[`captioner_prompt.md`](../prompts/captioner_prompt.md) to describe photos from
`data/media`. The prompt now highlights the overall vibe of the interior – for
example old Soviet, hotel-room style, modern, unfinished or antique. ``tg_client.py``
schedules ``caption.py`` right after an image
is stored, or if a stored file is missing its caption, so downloads continue in
parallel. Before sending to the API every picture is scaled so the shorter side
equals 512&nbsp;px, then ImageMagick's liquid rescale squeezes it down to
``512x512`` without cropping.
Each processed image gets a companion `*.caption.md` file stored beside the
original. Captions are later included in the lot chopper prompt where the
`chop.py` script lists every `Image <filename>` before its caption. This makes
it crystal clear which picture the text belongs to. When `LOG_LEVEL` is set to
`INFO`, the script logs each processed filename along with the generated
caption.
If some captions are missing you can run `make caption` to retry processing
all images.

See [chopper_prompt.md](../prompts/chopper_prompt.md) for the schema and taxonomy used by the
lot chopper. The prompt now includes short title examples and an `item:audience` field to mark
items for men, women or kids.

## chop.py
Feeds the message text plus any media captions to GPT-4o to extract individual
lots. `chop.py` marks the start of the original message with `Message text:` so
the LLM does not confuse it with captions. Each caption is preceded by its
filename. The script processes a single Markdown file path provided on the
command line and writes a matching JSON file under `data/lots`. The Makefile
queues only messages that lack a JSON result, preserving modification order, and
runs `chop.py` for each one using GNU Parallel so several messages are
processed at once. The API call specifies `response_format={"type":
"json_object"}` so GPT-4o returns plain JSON without Markdown wrappers.

## embed.py
Generates `text-embedding-3-large` vectors for each message file.  The output is
stored under `data/vectors/` mirroring the layout of `data/lots`.  GNU Parallel
processes the newest files first so search results are quickly refreshed.

Translations are now produced by `chop.py` itself.  Fields like
`title_ru` or `description_ka` are included in the lot JSON directly. Titles
use the street name together with room count, floor level and view where
applicable so that every language has a meaningful summary.

## build_site.py
Renders the static marketplace website using Jinja templates.  Lots are read
from `data/lots` and written to `data/views`.  The script loads
`ontology/fields.json` to order attribute tables and embeddings from `data/vectors` to suggest
similar lots.  Similarity search now uses `scikit-learn` to find nearest
neighbours efficiently. Each lot page shows images in a small carousel,
scaled to at most 40% of the viewport height, a table of
all recognised fields and a link back to the Telegram post.  Pages are
generated separately for every language configured in `config.py`.  The
navigation bar links to the same page in other languages instead of toggling via
JavaScript. Static files from `templates/static` are copied to
`data/views/static` so the site works without extra assets.
The index page now lists all `market:deal` categories with the number of
posts seen in the last ``KEEP_DAYS`` days and how many unique posters were involved.
Each category links to a separate page listing every lot of that type.
Lot pages include a "more by this user" section which shows other lots from the
same Telegram account ordered by vector similarity.  If a lot has a
timestamp that lies in the future it is ignored during rendering so the website
never displays misleading dates.

## alert_bot.py
Simple Telegram bot that lets users subscribe to notifications.  Alerts are sent
to all subscribers when new lots are detected.

## scan_ontology.py
Walks through `data/lots` and collects a list of every key used across all
stored lots. For each key the script counts how many times each value appears
and writes the result to `data/ontology/fields.json`. Titles and descriptions
are stored separately in JSON files with counts sorted by frequency. Lots
missing translated text are now treated the same as obviously mis-parsed ones
(for example those containing `contact:telegram` equal to `@username`) and all
go into `misparsed.json`. Each entry includes the exact text passed to the
lot parser under the `input` key so issues can be reproduced. After collecting the counts the script removes a few
noisy fields like timestamps and language specific duplicates so the output
focuses on meaningful attributes. Run `make ontology` to generate the files for
manual inspection.
Lots flagged as misparsed are ignored by `build_site.py` so the website never
shows incomplete posts.
Any raw post lacking mandatory metadata is added to `broken_meta.json` so
`tg_client.py` can refetch it during the next run.

## moderation.py
Reusable library for spam filtering. `moderation.apply_to_history()` walks
through `data/lots` and removes any entries whose raw post text matches banned
phrases. The checks also run inside `chop.py` and `build_site.py` so unwanted
posts never reach the website. Update the library with new rules and rerun the
script to clean past data.

## Makefile
The `Makefile` in the repository root wires these scripts together.  Running
`make compose` performs a full refresh: pulling messages (images are captioned on
the fly), chopping, embedding and rebuilding the static site.  `make update` is kept as a
compatibility alias for older instructions.

## Validation
Pipeline stages rely on the previous step's output. The Makefile runs
`scripts/validate_outputs.py` after captions, chopping and embedding to ensure
files are ready for the next phase. See [validation.md](validation.md) for the
checks performed.
