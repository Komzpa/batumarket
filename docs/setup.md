# Setup and Usage

This project uses Python 3.12. Install dependencies and run the services via the Makefile.

```bash
python -m venv .venv
source .venv/bin/activate
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
