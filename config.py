# Central configuration for tokens and service URLs

# OpenAI API key for chat completion and embeddings
OPENAI_API_KEY = "sk-.."

# Models preferred for chat completions
AVAILABLE_MODELS = [
    #{"model": "gpt-4.1"},
    #{"model": "gpt-4.1-mini"},
    #{"model": "o1"},
    #{"model": "o3", "reasoning_effort": "high", "service_tier": "flex"},
    #{"model": "o4-mini", "reasoning_effort": "high", "service_tier": "flex"},
]

# Models used for intermediate place reviews
SMALL_REVIEW_MODELS = [
    {"model": "gpt-4o", "service_tier": "flex"},
    {"model": "o4-mini", "reasoning_effort": "high", "service_tier": "flex"},
    {"model": "o4-mini", "service_tier": "flex"},
    {"model": "o3", "service_tier": "flex"},
]
