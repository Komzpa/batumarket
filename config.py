# Configuration constants for Batumarket services.
# Secrets must be kept outside the repository.

TG_TOKEN = "123:ABC"  # Used by alert_bot.py

# Telethon client configuration.  ``TG_API_ID`` and ``TG_API_HASH`` identify
# the application while ``TG_SESSION`` stores the logged in user session.
TG_API_ID   = 123456
TG_API_HASH = "0123456789abcdef0123456789abcdef"
TG_SESSION  = "session"

# Chats to mirror.  Keep them as text usernames to avoid accidental numeric
# ID confusion.  Telethon accepts the same strings directly.
CHATS = ["baraholka_ge", "baraholka_avito_batumi"]

OPENAI_KEY = "sk-..."

DB_DSN = "postgresql:///bazaar"

# Target languages for translations
LANGS = ["ru", "en"]
