# Batumarket

Tools for mirroring Telegram "Барахолка" style chats and building a small AI powered marketplace.  The parser now uses [Telethon](https://github.com/LonamiWebs/Telethon) to operate a normal user account.  Message history is fetched incrementally with a ``KEEP_DAYS`` cap so the initial sync finishes quickly.  Each service is a Python script invoked from the Makefile at the repository root.
Large back-fills download messages in parallel when ``DOWNLOAD_WORKERS`` is set
in `config.py`.

See [docs/services.md](docs/services.md) for an overview of the scripts.
For installation instructions see [docs/setup.md](docs/setup.md).
The project goals are described in [docs/vision.md](docs/vision.md).
Approximate OpenAI expenses are outlined in [docs/costs.md](docs/costs.md).
[Maintenance instructions](docs/maintenance.md) cover how to keep translations up to date.
[Output validation](docs/validation.md) explains the checks that run after every pipeline stage.
[Ontology housekeeping](docs/ontology_housekeeping.md) describes how to keep the
generated field counts in sync and refine prompts. If `data/raw` is missing the
scanner should not run as it would produce empty files – review the tracked
JSONs instead.

The ontology files include `broken_meta.json` which lists messages missing
metadata. `tg_client.py` tries to refetch everything in that list at the start
of each run.

Logs are written to `errors.log` in JSON format. Set `LOG_LEVEL` in
`config.py` or as an environment variable to `DEBUG`, `INFO` or `ERROR` to
adjust verbosity. When the level is `INFO`, `tg_client.py` logs each
captioned file along with the generated text. Run `make caption` to
(re)process any images that might have missed automatic captioning. Unicode
characters, including Cyrillic, are stored verbatim so logs remain easy to
read.

Domain specific helpers like `src/post_io.py`, `src/lot_io.py` and
`src/caption_io.py` provide validated loading and saving of posts,
lots and captions.  They build on `src/serde_utils.py` so every stage
creates directories automatically and logs parsing errors once.
