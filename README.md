# Batumarket

Tools for mirroring Telegram "Барахолка" style chats and building a small AI powered marketplace.  The parser now uses [Telethon](https://github.com/LonamiWebs/Telethon) to operate a normal user account.  Message history is fetched incrementally with a 31 day cap so the initial sync finishes quickly.  Each service is a Python script invoked from the Makefile at the repository root.

See [docs/services.md](docs/services.md) for an overview of the scripts.
For installation instructions see [docs/setup.md](docs/setup.md).
The project goals are described in [docs/vision.md](docs/vision.md).
