# Commands use "python" directly so they can be copy/pasted

# Define pipeline stages explicitly so ``make -j compose`` executes them in the
# correct order.  Each stage runs only after its dependency completes.
.PHONY: compose update pull caption chop embed build alert ontology clean precommit

# ``compose`` is the main entry point used by documentation and tests.  ``update``
# remains as a backwards compatible alias.
compose: build
update: compose

# Pull Telegram messages and media to ``data/``.
pull:
	python src/tg_client.py

# Generate image captions for files missing ``*.caption.md``.
caption: pull
	find data/media -type f ! -name '*.md' -printf '%T@ %p\0' \
	| sort -z -nr \
	| cut -z -d' ' -f2- \
	| parallel -0 python src/caption.py

# Split messages into lots using captions and message text.
chop: pull
	python scripts/pending_chop.py \
	| parallel -0 python src/chop.py

# Store embeddings for each lot in JSON files using GNU Parallel.
embed: chop
	python scripts/pending_embed.py \
	| parallel -0 python src/embed.py

# Render HTML pages from lots and templates.
build: embed ontology
	python src/build_site.py

# Telegram alert bot for new lots.
alert:
	python src/alert_bot.py

ontology:
	python src/scan_ontology.py

clean:
	rm -rf data/views/*

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
