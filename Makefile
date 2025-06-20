PYTHON=python

# Define pipeline stages explicitly so ``make -j compose`` executes them in the
# correct order.  Each stage runs only after its dependency completes.
.PHONY: compose update pull caption chop embed build alert ontology clean precommit

# ``compose`` is the main entry point used by documentation and tests.  ``update``
# remains as a backwards compatible alias.
compose: build
update: compose

# Pull Telegram messages and media to ``data/``.
pull:
	$(PYTHON) src/tg_client.py

# Generate image captions for files missing ``*.caption.md``.
caption: pull
	find data/media -type f ! -name '*.md' -printf '%T@ %p\0' \
	| sort -z -nr \
	| cut -z -d' ' -f2- \
	| parallel -0 $(PYTHON) src/caption.py

# Split messages into lots using captions and message text.
chop: pull
	$(PYTHON) src/chop.py

# Store embeddings for each lot in Postgres and JSONL.
embed: chop
	$(PYTHON) src/embed.py

# Render HTML pages from lots and templates.
build: embed
	$(PYTHON) src/build_site.py

# Telegram alert bot for new lots.
alert:
	$(PYTHON) src/alert_bot.py

ontology:
	$(PYTHON) src/scan_ontology.py

clean:
	rm -rf data/views/*

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
