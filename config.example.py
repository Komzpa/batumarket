"""Example configuration for Batumarket services.

Copy this file to ``config.py`` and replace the placeholder values with your
own credentials.  Secrets should never be committed to the repository.
"""

# Telegram bot token used by ``alert_bot.py``.  Create a bot with BotFather and
# paste the token here.
TG_TOKEN = "123:ABC"

# Telethon client credentials.  ``TG_API_ID`` and ``TG_API_HASH`` identify the
# application, while ``TG_SESSION`` is a filename where the user session will be
# saved after the first login.
TG_API_ID = 123456
TG_API_HASH = "0123456789abcdef0123456789abcdef"
TG_SESSION = "session"

# List of Telegram chat usernames to mirror.  Keep them as strings to avoid
# confusion with numeric IDs.  Example values below follow popular Georgian
# flea-market groups.
CHATS = ["baraholka_ge", "baraholka_avito_batumi"]

# OpenAI API key used for captioning, chopping and translating.
OPENAI_KEY = "sk-..."


# Languages used when parsing lots.  ``chop.py`` will generate title and
# description fields for each entry in this list.
LANGS = ["en", "ru", "ka"]

# How many days of history to keep on disk
KEEP_DAYS = 7


