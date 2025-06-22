# Service Overview

This repository powers a small Telegram marketplace.  Each Python script in
`src/` acts as a stand-alone service invoked from the Makefile.  See
[`setup.md`](setup.md) for installation instructions.

## tg_client.py
Uses Telethon to mirror the target chats as a normal user account.

* **Chat access.** At startup the client checks that the account has already
  joined every chat listed in `CHATS`, joining any missing private channels so
  their history is accessible.
* **Topic filter.** Add `chat/topic_id` entries to `CHATS` when you only want a
  specific forum thread. Messages from other topics are ignored.
* **Back-fill strategy.** The client keeps only the last ``KEEP_DAYS`` days on
  disk.  When fetching history it jumps straight to the cut-off date instead of
  scrolling from the very first message.  If less than ``KEEP_DAYS`` days are
  stored the client now pulls the entire missing range in one go so the history
  catches up immediately.  Once the full threshold is present only newer
  messages are pulled.
* **Realtime updates.** Pass ``--listen`` to `tg_client.py` to keep running after
  the initial sync.  Without this flag the client exits once everything is
  synced so the Makefile can continue.
* **Manual debug.** ``--fetch <chat> <id>`` downloads one message for
  inspection and exits after printing its text to the logs.
* **Granular sync.** ``--ensure-access`` joins chats, ``--refetch`` reloads
  incomplete posts and ``--fetch-missing`` pulls new history. Omitting these
  flags runs all three in sequence.
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
  extension.  The client listens on ``events.Album`` so every attachment arrives
  grouped.  If some segments are missing nearby messages are fetched by
  ``grouped_id`` to avoid incomplete posts.  Messages that disappear from
  Telegram during the last ``KEEP_DAYS`` days are
  removed from disk while edits overwrite the Markdown in place.
* **Resume state.** The timestamp of the last processed batch is stored under
  `data/state/<chat>.txt` so interrupted runs continue from the same point.
  Progress older than the current `KEEP_DAYS` window is ignored so lowering the
  threshold does not re-fetch deleted history. Attachments that fail to download
  are skipped with a warning and the reason is stored under `skipped_media` in
  the message metadata. The client ignores videos (`.mp4`), audio files, images
  larger than ten megabytes and any media attached to messages more than two
  days old. Messages marked this way are ignored by `chop.py` so only complete
  posts are parsed. When the media was downloaded previously the field is left
  out so older posts keep their files intact.
* **Automatic cleanup.** Messages listed in `broken_meta.json` or posts saved
  without text or images are reloaded on startup. If the content changed their
  corresponding lot files are removed so the parser runs again.

Metadata fields include at least:

- `id`, `chat`, `date`, `reply_to`, `is_admin`
- `sender` (numeric when available), `sender_name`, `sender_username`,
  `sender_phone`, `post_author`, `tg_link`, `author_type`
- `sender_chat` when the post comes from a channel or anonymous admin
- `source:author:telegram`, `source:author:name` – copied into every lot for
  fallback when contact details are missing
- `group_id` if part of an album
- `files` – list of stored media paths without duplicates
- `skipped_media` – reason string when attachments were not downloaded; omitted
  when the file was already stored

When contact information is missing `tg_client.py` logs a single warning with
the full message metadata and skips the post so issues can be investigated.

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
caption. `tg_client.py` keeps a queue of freshly written posts together with
any images still waiting for captions. Each queued item cools down for about
twenty seconds so additional album messages can arrive. Once all captions are
present (or there were no images) and the cooldown expires the client spawns
`chop.py` in the background. This way lots appear quickly without waiting for
the next `make chop` run and incomplete posts are avoided.
If some captions are missing you can run `make caption` to retry processing
any uncaptured images. The command skips files that already have captions so
the API isn't called unnecessarily.
Pictures from posts rejected by `moderation.should_skip_message` are ignored so
spam never reaches the captioning stage.

See [chopper_prompt.md](../prompts/chopper_prompt.md) for the schema and taxonomy used by the
lot chopper. The prompt now includes short title examples and an `item:audience` field to mark
items for men, women or kids. Ads posted to the wrong chat
(like a job offer in a real-estate group) are marked with
`fraud=spam` even when they look legitimate.

## chop.py
Feeds the message text plus any media captions to GPT-4o to extract individual
lots. `chop.py` marks the start of the original message with `Message text:` so
the LLM does not confuse it with captions. Each caption is preceded by its
filename. The script processes a single Markdown file path provided on the
command line and writes a matching JSON file under `data/lots`. The Makefile
queues only messages that lack a JSON result, preserving modification order, and
runs `chop.py` for each one using GNU Parallel so several messages are
processed at once. Posts flagged by `moderation.should_skip_message` are
excluded from this list so the parser never wastes API calls on obvious spam.
The API call specifies `response_format={"type":
"json_object"}` so GPT-4o returns plain JSON without Markdown wrappers.

## embed.py
Generates `text-embedding-3-large` vectors for each lot.  The output is stored
under `data/vectors/` mirroring the layout of `data/lots`.  Each file contains a
list of `{id, vec}` pairs so multiple lots share a single vector file.  GNU
Parallel processes the newest files first so search results are quickly
refreshed. `pending_embed.py` upgrades any leftover single-object files by
wrapping them in a list and deletes mismatched ones so stale vectors never pollute
the index. Files from moderated posts are skipped entirely so no vectors are
stored for spam.

Translations are now produced by `chop.py` itself.  Fields like
`title_ru` or `description_ka` are included in the lot JSON directly. Titles
use the street name together with room count, floor level and view where
applicable so that every language has a meaningful summary.

## build_site.py
Renders the static marketplace website using Jinja templates.  Lots are read
from `data/lots` and written to `data/views`.  The script loads
`ontology/fields.json` to order attribute tables and embeddings from `data/vectors` to suggest
similar lots.  Vector files without a matching lot are dropped before computing
similarity so stale data never bloats memory. Similarity search now uses `scikit-learn` to find nearest
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
are stored separately in JSON files with counts sorted by frequency.
Lots missing translated text or a timestamp, as well as posts without any seller
information, are treated the same as obviously mis-parsed ones (for example
those containing `contact:telegram` equal to `@username`) and all go into
`misparsed.json`. Each entry includes the exact text passed to the lot parser
under the `input` key so issues can be reproduced. Raw posts missing contact
details or a timestamp are flagged too. Both this script and `build_site.py`
rely on helper functions in `lot_io.py` and `post_io.py` to pick the seller and
validate timestamps. After collecting the counts the script removes a few
noisy fields like timestamps and language specific duplicates so the output
focuses on meaningful attributes. Run `make ontology` to generate the files for
manual inspection.
Lots containing a `fraud` field are listed separately in `fraud.json` with the text that produced them.
If `data/raw` is not present the script will exit early to avoid overwriting the
tracked JSON files. In that case simply review what is already under
`data/ontology`.
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
Recent filters catch offers of illegal narcotics and vague job ads like
"ищу людей на неполный рабочий день" so they never reach the website.
Loan promises or token giveaways ("Дам в долг", "Помогу с деньгами", "чем раньше они войдут, тем больше смогут забрать в халявной раздаче токенов") are treated as scams.
Job offers quoting salary in Russian roubles are considered sketchy for Georgia where wages are usually in GEL or USD.

Some chats are cluttered with housekeeping bots. ``tg_client.py`` consults
``moderation.BLACKLISTED_USERS`` and drops their updates without downloading
media. The initial blacklist contains ``M_S_Help_bot``, ``ChatKeeperBot``,
``DosviduliBot`` and ``Batumi_Batumi_bot``.

## File I/O helpers
`post_io.py`, `lot_io.py`, `caption_io.py` and `image_io.py` handle posts,
lots, captions and media metadata. They use `serde_utils.py` for the low-level
JSON or Markdown handling so each script works with cleaned data and missing
directories are created automatically.
`lot_io.py` provides helper functions like `get_seller()` and
`get_timestamp()` which both the ontology scanner and site builder use to stay
in sync.

## debug_dump.py
Collects everything related to a single lot into one text block.
Pass a page URL and the script will trim the hostname, run
`tg_client.py --fetch` on the underlying Telegram post and then append
the resulting logs along with the lot JSON, vector file and raw post.
Captions and image metadata are included when present so the entire
pipeline state can be shared in one go. If the lot JSON is missing the
chat name and message ID are extracted from the page path so Telegram
can still be queried.
Standard error from the Telegram client is also captured so dependency
issues are visible. Use `--refresh` to drop any cached files and
reprocess the lot before dumping.

## Makefile
The `Makefile` in the repository root wires these scripts together. Running
`make compose` performs a full refresh: pulling messages (images are captioned on
the fly), chopping, embedding and rebuilding the static site. Missing posts are
pruned with `make removed` which depends on the main sync and ends by calling
`make clean` so stray files never linger. The build phase depends on this step
but when run with `-j` it proceeds in the background. `make update` remains as a
compatibility alias for older instructions.

## Validation
Pipeline stages rely on the previous step's output.
Each stage now checks that required files are present so the pipeline fails early.
See [validation.md](validation.md) for the checks performed.
