# Commands use "python" directly so they can be copy/pasted

# Define pipeline stages explicitly so ``make -j compose`` executes them in the
# correct order.  Each stage runs only after its dependency completes.
.PHONY: compose update pull removed caption chop embed build alert ontology clean precommit debugdump

all: clean build deploy removed

pull: # Pull Telegram messages and media to ``data/``.
	python src/tg_client.py --ensure-access --fetch-missing

removed: pull ## Drop local posts removed from Telegram and tidy leftover files.
	$(MAKE) clean # remove previously half-cleaned leftovers
	python src/scan_ontology.py # re-collect what still needs to be fetched
	python src/tg_client.py --refetch --check-deleted
	$(MAKE) clean # remove newly created leftovers

caption: pull ## Generate image captions for files missing ``*.caption.md``.
	python scripts/pending_caption.py | parallel --eta -j16 -0 python src/caption.py

chop: pull caption ## Split messages into lots using captions and message text.
	python scripts/pending_chop.py | parallel --eta -j16 -0 python src/chop.py

ontology: chop ## Summarize lots so it's easier see what exactly is there in the dataset.
	python src/scan_ontology.py

# Store embeddings for each lot in JSON files using GNU Parallel.
embed: chop caption
	python scripts/pending_embed.py | parallel --eta -j16 -0 python src/embed.py

# Render HTML pages from lots and templates.
build: embed ontology
	rm -rf data/views/*
	python src/build_site.py

deploy: build ## Deploy built static website to the server
	rsync --delete-after --size-only -zz --compress-choice=zstd --compress-level=3 --omit-dir-times --omit-link-times --info=stats2,progress2 -aH -e "ssh -T -c aes128-ctr -o Compression=no" data/views/ 178.62.209.164:/srv/www/batumarket/

# Telegram alert bot for new lots.
alert: embed
	python src/alert_bot.py

# Gather logs and related files for one lot.
debugdump:
	python src/debug_dump.py "$(URL)"

clean:
	python src/clean_data.py

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
	python scripts/check_translations.py
