# Setup and Usage

This project uses Python 3.12.  On Debian based distributions the required
modules are available as packages:

```bash
sudo apt install python3-openai \
    python3-python-telegram-bot \
    python3-jinja2 \
    python3-structlog python3-telethon \
    python3-sklearn python3-progressbar2 \
    python3-html5lib \
    gettext  # provides msgfmt used to compile translations
```

If you prefer isolated dependencies create a virtual environment and use the
`requirements.txt` file instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Copy the example configuration and edit it with your credentials:

```bash
cp config.example.py config.py
```

Copy `config.example.py` to `config.py` and fill in the secrets or export the
variables before running any script:
- `TG_TOKEN` – Telegram bot token used by the alert bot
- `TG_API_ID` / `TG_API_HASH` – credentials for the Telethon client
- `TG_SESSION` – filename where the logged in user session will be stored
- `CHATS` – list of chat usernames to mirror.  A slash followed by a numeric
  topic ID restricts syncing to that forum thread (e.g. `dogacat_batumi/136416`).
  The client joins each chat automatically if needed.
- `OPENAI_KEY` – API key for OpenAI models
- `CHOP_MODELS` – list of model parameters tried when parsing lots
- `DOWNLOAD_WORKERS` – how many messages to fetch in parallel during the initial sync

Use the Makefile in the repository root to run the pipeline:

```bash
make compose
```

`make update` continues to work as an alias for this pipeline.

This pulls messages (images are captioned immediately and lots are parsed in the background). Chopped lots trigger embedding right away so vectors stay in sync without a separate step. The command finishes by building the static site.
Run `make caption` or `make chop` separately if you need to reprocess failed images.
`make caption` now skips files that already have captions so reruns are cheap.

Run the test suite and linter before committing:

```bash
make precommit
pytest
```

For offline smoke tests you can enable testing mode:

```bash
TEST_MODE=1 PYTHONPATH=. make -B -j compose
```
