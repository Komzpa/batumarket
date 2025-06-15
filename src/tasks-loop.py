import testing_mode
testing_mode.apply_testing_mode()

import openai
import requests
import json
from datetime import datetime
import time
import random
from Config import config
import os
from log_utils import get_logger, install_excepthook
from token_utils import estimate_tokens
from llm_utils import call_with_fallback
from notes_utils import collect_notes, read_md, write_md

log = get_logger().bind(script=__file__)
install_excepthook(log)

# Set OpenAI API key
openai.api_key = config.OPENAI_API_KEY

def generate_quick_replies(text):
    """Return short quick‑reply buttons for Telegram.

    Buttons are short reports about mood or confirmation of actions
    already taken. They are not instructions.
    """

    system_prompt = read_md("Prompts/telegram_quick_reply.md")
    log.debug("QR system tokens", count=estimate_tokens(system_prompt))
    log.debug("QR user tokens", count=estimate_tokens(text))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    try:
        raw = call_with_fallback(messages, config.SMALL_REVIEW_MODELS)
        raw = raw.strip()
        log.debug("Quick reply raw", raw=raw)
        replies = json.loads(raw)
        return [str(r) for r in replies[:3]]
    except Exception:
        log.exception("Failed to generate quick replies")
        return []



now = datetime.now()

msgs_list = []
# Load assistant system prompt and examples if present
system_files = ["Prompts/reemxy.md", "Prompts/reemxy_examples.md"]
system_content = "\n".join(read_md(f) for f in system_files if os.path.exists(f))
msgs_list.append(
    "Possible venues around you:\n\n" +
    read_md("Intermediate/Candidate Places.md")
)
msgs_list.append(
    "People to contact:\n\n" +
    read_md("Intermediate/Contacts.md")
)
msgs_list.append(
    "Social activities:\n\n" +
    read_md("Intermediate/Social Activities.md")
)
msgs_list.append(
    "Various notes from user's notes document:\n\n" +
    collect_notes().replace('\\n', '\n')
)
msgs_list.append(
    "Past and upcoming 48h plan:\n\n" +
    read_md("Intermediate/Hourly Plan.md")
)
msgs_list.append(now.strftime("Now is %A, %Y-%m-%d %H:%M:%S GET. ") + "Day " + str(int(1 + (time.time() / 86400) % 3)) + " of 3 day cycle.")
# Attach collected errors so the assistant can inform the user
errors = read_md("Intermediate/errors.log")
if errors.strip():
    msgs_list.append("Errors during pipeline:\n" + errors)
messages = []


messages.append({"role": "system", "content": system_content})
messages.append({"role": "user", "content": '\n'.join(msgs_list)})
log.info("System tokens", count=estimate_tokens(system_content))
log.info("Prompt tokens", count=estimate_tokens(messages[1]["content"]))

# List out the models (with optional parameters).
# For any parameter beyond 'model' itself, include them in a dictionary.
available_models = config.AVAILABLE_MODELS.copy()

# Shuffle them to pick at random.
random.shuffle(available_models)

message_text = None
error_log_to_send = None

# Record the prompt fed to the model for debugging. ``write_md`` keeps a
# trailing newline so the file can be concatenated if needed.
write_md("Intermediate/Latest Prompt.md", messages[1]["content"])

# Get the assistant's final reply using fallback models
try:
    message_text = call_with_fallback(messages, available_models)
    log.info("Response tokens", count=estimate_tokens(message_text))
    error_log_to_send = None
except Exception:
    log.exception("All models failed")
    message_text = None
    error_log_to_send = read_md("Intermediate/errors.log")


# Write to sent messages log
if message_text:
    logfile = open("Intermediate/Sent Messages.md", "a")
    logfile.write(now.strftime("\n\nReemxy at %A, %Y-%m-%d %H:%M:%S. \n"))
    logfile.write(message_text)
    logfile.close()


# Send to Telegram
telegram_token = config.TELEGRAM_TOKEN
chat_id = config.TELEGRAM_CHAT_ID

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    quick_replies = generate_quick_replies(text)
    if quick_replies:
        reply_markup = json.dumps({
            'keyboard': [[r] for r in quick_replies],
            'one_time_keyboard': True,
            'resize_keyboard': True,
        })
    else:
        reply_markup = None
    payload = {
        'chat_id': chat_id,
        'text': text[:4000],
        'parse_mode': 'Markdown',
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        log.info("Sent Telegram message", chat_id=chat_id)
    except requests.exceptions.HTTPError as e:
        # This handles HTTP errors
        log.error("HTTP error", error=str(e), body=response.text)
    except requests.exceptions.RequestException as e:
        # This handles other types of requests exceptions
        log.error("Error sending message", error=str(e))

if error_log_to_send:
    send_telegram_message(error_log_to_send)
    raise RuntimeError("All models failed. Please check the errors above.")
send_telegram_message(message_text)
