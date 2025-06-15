import testing_mode
testing_mode.apply_testing_mode()

import openai
from Config import config
from log_utils import get_logger

log = get_logger().bind(script=__name__)

openai.api_key = config.OPENAI_API_KEY


def call_with_fallback(messages, model_list):
    """Try models in order until one succeeds."""
    for params in model_list:
        log.info("Calling model", model=params)
        try:
            # Flex tier can respond slowly, bump timeout to 15 minutes.
            response = openai.chat.completions.create(
                messages=messages,
                timeout=900,
                **params
            )
            log.info("Model succeeded", model=params)
            return response.choices[0].message.content
        except Exception:
            # Errors here are logged and the next model attempted.
            log.exception("Failed with parameters", model=params)
    raise RuntimeError("All models failed. Please check the errors above.")
