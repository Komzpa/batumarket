"""Example configuration for Batumarket services.

Copy this file to ``config.py`` and replace the placeholder values with your
own credentials.  Secrets should never be committed to the repository.
"""

# Telegram bot token used by ``telegram_bot.py``.  Create a bot with
# BotFather and paste the token here.  The same token powers both the
# interactive bot and the HTTP API.
TG_TOKEN = "123:ABC"

# Telethon client credentials.  ``TG_API_ID`` and ``TG_API_HASH`` identify the
# application, while ``TG_SESSION`` is a filename where the user session will be
# saved after the first login.
TG_API_ID = 123456
TG_API_HASH = "0123456789abcdef0123456789abcdef"
TG_SESSION = "session"

# List of Telegram chat usernames to mirror.  Each entry may optionally
# include a forum topic ID after a slash to restrict the sync.  For example
# ``"dogacat_batumi/136416"`` mirrors only that topic from the group while
# ``"baraholka_ge"`` grabs the entire chat.  Duplicate chat names are ignored
# and a bare chat entry overrides any topic filters listed earlier.
CHATS = [
    "baraholka_ge",
    "baraholka_avito_batumi",
    # "dogacat_batumi/136416",  # ищу дом
]

# OpenAI API key used for captioning, chopping and translating.
OPENAI_KEY = "sk-..."

# Models used to chop posts into lots. The parser tries them in order until a
# result passes basic validation.
CHOP_MODELS = [
    {"model": "gpt-4o-mini"},
    {"model": "gpt-4o"},
]


# Languages used when parsing lots.  ``chop.py`` will generate title and
# description fields for each entry in this list.
LANGS = ["en", "ru", "ka"]

# How many days of history to keep on disk
KEEP_DAYS = 7

# Default log verbosity. Use "DEBUG", "INFO" or "ERROR".
LOG_LEVEL = "INFO"

# Number of messages to process in parallel when fetching history.  Higher
# values speed up downloads at the risk of hitting Telegram rate limits.
DOWNLOAD_WORKERS = 4


