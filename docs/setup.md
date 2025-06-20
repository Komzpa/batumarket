# Setup and Usage

This project uses Python 3.12.  On Debian based distributions the required
modules are available as packages:

```bash
sudo apt install python3-openai \
    python3-python-telegram-bot \
    python3-psycopg2 python3-jinja2 \
    python3-structlog python3-telethon
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
- `CHATS` – list of chat or channel usernames to mirror.  The client will join
  them automatically if needed.
- `OPENAI_KEY` – API key for OpenAI models
- `DB_DSN` – PostgreSQL DSN used by embedding storage

Use the Makefile in the repository root to run the pipeline:

```bash
make update
```

This pulls messages, captions images, chops lots, generates embeddings and finally builds the static site.

Run the test suite and linter before committing:

```bash
make precommit
pytest
```

For offline smoke tests you can enable testing mode:

```bash
TEST_MODE=1 PYTHONPATH=. make -B -j compose
```
