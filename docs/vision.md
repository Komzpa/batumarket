# Project Vision

The long term goal is to build an AI driven marketplace website. Telegram chats such as "Барахолка" or "Отдам даром" are mirrored and processed to produce structured listings.

Components involved:

- **Database** – a git repository containing Markdown and images from the ads. It should be easy to update and consume new data.
- **Telegram bot** – monitors configured chats and saves raw messages and photos. Deleted or sold items are marked based on Telegram edits.
- **Chopper** – splits posts into individual lots, pairing images with the correct text fragments. Captions are passed as `Image <filename>` blocks so the model knows which picture is which. The result is a machine‑readable JSON inspired by OpenStreetMap tags while keeping links to the original message. OpenAI APIs are used here.
- **Indexer** – generates embeddings for each lot to enable search and "similar items" suggestions.
- **Browser** – renders the database as static HTML so it is easily crawled by search engines.
- **Alerter** – notifies subscribers on Telegram when new lots match their interests. The same bot can be reused for alerts.

Automation is orchestrated by the Makefile which chains the scripts together.
