from Config import config
from llm_utils import call_with_fallback
from log_utils import get_logger, install_excepthook
from token_utils import estimate_tokens
from notes_utils import read_text, write_md
import testing_mode

testing_mode.apply_testing_mode()

log = get_logger().bind(script=__file__)
install_excepthook(log)

RAW_LOG = 'Intermediate/Telegram Log.md'
SENT_LOG = 'Intermediate/Sent Messages.md'
OUTPUT = 'Intermediate/Telegram Notes.md'
PROMPT_FILE = 'Prompts/process_telegram_updates.md'

raw_text = read_text(RAW_LOG)
sent_text = read_text(SENT_LOG)

log_lines = raw_text.splitlines()[-60:]
sent_lines = sent_text.splitlines()[-20:]

from notes_utils import read_md

prompt_template = read_md(PROMPT_FILE)

prompt = prompt_template.format(LOG='\n'.join(log_lines), SENT='\n'.join(sent_lines))

log.info("Prompt tokens", count=estimate_tokens(prompt))

messages = [{"role": "user", "content": prompt}]

try:
    result = call_with_fallback(messages, config.SMALL_REVIEW_MODELS)
    text = result.strip()
except Exception:
    log.exception("Failed to process telegram updates")
    text = '\n'.join(log_lines)

write_md(OUTPUT, text)
print(text)
