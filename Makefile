# Commands use "python" directly so they can be copy/pasted

# Define pipeline stages explicitly so ``make -j compose`` executes them in the
# correct order.  Each stage runs only after its dependency completes.
.PHONY: compose update pull removed caption chop embed build alert ontology clean precommit debugdump callgraph install-dependencies test

all: clean build deploy removed ## Clean, build, deploy and prune removed posts

pull: ## Pull Telegram messages and media to ``data/``.
	python src/tg_client.py --ensure-access --fetch-missing

REMOVED_STAMP ?= data/.removed-stamp

# Run cleanups only once after midnight. Subsequent invocations exit quickly
removed: pull ## Drop local posts removed from Telegram and tidy leftover files.
	@stamp=$(REMOVED_STAMP); \
	today=$$(date -I); \
	mkdir -p $$(dirname $$stamp); \
	if [ "$$today" = "$$(cat $$stamp 2>/dev/null)" ]; then \
	echo "Already pruned today"; \
	else \
	echo "$$today" > $$stamp; \
	$(MAKE) clean; \
	python src/scan_ontology.py; \
	python src/tg_client.py --refetch --check-deleted; \
	$(MAKE) clean; \
	fi

caption: pull ## Generate image captions for files missing ``*.caption.json``.
	python scripts/pending_caption.py | parallel --eta -j16 -0 python src/caption.py

chop: pull caption ## Split messages into lots using captions and message text.
	python scripts/pending_chop.py | parallel --eta -j16 -0 python src/chop.py || true

ontology: chop ## Summarize lots so it's easier see what exactly is there in the dataset.
	python src/scan_ontology.py

embed: chop caption ## Store embeddings for each lot
	python scripts/pending_embed.py | parallel --eta -j16 -0 python src/embed.py

similar: embed ## Compute lot recommendations
	python src/similar.py

prices: embed # Train price regression model and save it under ``data/price_model.json``.
	python src/price_train.py

clusters: embed ## Group item types into clusters
	python src/cluster_items.py

build: prices similar clusters ontology ## Render HTML pages from lots and templates
	rm -rf data/views/*
	python src/build_site.py

deploy: build ## Deploy built static website to the server
	rsync --delete-before --size-only -zz --compress-choice=zstd --compress-level=3 --omit-dir-times --omit-link-times --info=stats2,progress2 -aH -e "ssh -T -c aes128-ctr -o Compression=no" data/views/ 178.62.209.164:/srv/www/batumarket/

alert: embed ## Notify about new lots
	python src/telegram_bot.py

debugdump: ## Dump logs for a single lot
	python src/debug_dump.py "$(URL)"

clean: ## Delete all temporary files
	python src/clean_data.py

install-dependencies: ## Install system packages and Python modules used in tests
	@sudo apt-get install -y \
	python3-openai \
        python3-sklearn \
	python3-python-telegram-bot \
	python3-telethon \
	python3-jinja2 \
	python3-structlog \
	python3-progressbar2 \
	python3-html5lib \
	python3-pytest \
	python3-pytest-cov \
	python3-graphviz \
	graphviz \
	gettext


precommit: ## Run pre-commit checks
	make callgraph
	find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
	python scripts/check_translations.py

test: precommit ## Run linter and unit tests with coverage
	pytest -v --cov=src --cov-report=term-missing --cov-report=xml

callgraph: ## Generate call graph diagram
	python scripts/function_callgraph.py | unflatten -l 3 -f -c 6 > docs/callgraph.dot && dot -Tsvg docs/callgraph.dot -o docs/callgraph.svg
