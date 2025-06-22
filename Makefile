# Commands use "python" directly so they can be copy/pasted

# Define pipeline stages explicitly so ``make -j compose`` executes them in the
# correct order.  Each stage runs only after its dependency completes.
.PHONY: compose update pull caption chop embed build alert ontology clean precommit validate

# ``compose`` is the main entry point used by documentation and tests.  ``update``
# remains as a backwards compatible alias.
compose: build
update: compose


pull: # Pull Telegram messages and media to ``data/``.
	python src/tg_client.py

caption: pull ## Generate image captions for files missing ``*.caption.md``.
	python scripts/pending_caption.py \
	| parallel -j16 -0 python src/caption.py
	python scripts/validate_outputs.py captions

chop: pull caption ## Split messages into lots using captions and message text.
	python scripts/pending_chop.py | parallel -j16 -0 python src/chop.py
	python scripts/validate_outputs.py lots

ontology: chop ## Summarize lots so it's easier see what exactly is there in the dataset.
	python src/scan_ontology.py

# Store embeddings for each lot in JSON files using GNU Parallel.
embed: chop caption
	python scripts/pending_embed.py | parallel -j16 -0 python src/embed.py
	python scripts/validate_outputs.py vectors


# Render HTML pages from lots and templates.
build: embed ontology
	rm -rf data/views/*
	python src/build_site.py

# Telegram alert bot for new lots.
alert: embed
	python src/alert_bot.py

validate:
	python scripts/validate_outputs.py

clean:
	python src/clean_data.py

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
	python scripts/check_translations.py
