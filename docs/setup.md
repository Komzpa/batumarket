# Setup and Usage

This project uses Python 3.12.  On Debian based distributions the required
modules are available as packages:

```bash
sudo apt install python3-openai \
    python3-python-telegram-bot \
    python3-psycopg2 python3-jinja2 \
    python3-structlog
```

If you prefer isolated dependencies create a virtual environment and use the
`requirements.txt` file instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Set up the required environment variables in `config.py` or export them before running any script:
- `TG_TOKEN` – Telegram bot token
- `CHATS` – list of chat IDs to mirror
- `OPENAI_KEY` – API key for OpenAI models
- `DB_DSN` – PostgreSQL DSN used by embedding storage

Use the Makefile in `src/` to run the pipeline:

```bash
make -f src/Makefile update
```

This pulls messages, captions images, chops lots, generates embeddings, translates them and finally builds the static site.

Run the test suite and linter before committing:

```bash
make -f src/Makefile precommit
pytest
```

For offline smoke tests you can enable testing mode:

```bash
TEST_MODE=1 PYTHONPATH=. make -B -j -f src/Makefile compose
```
