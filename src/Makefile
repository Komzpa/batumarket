PYTHON=python

update: pull chop caption embed translate build

pull: src/tg_client.py
	$(PYTHON) src/tg_client.py

caption: src/caption.py
	$(PYTHON) src/caption.py

chop: src/chop.py
	$(PYTHON) src/chop.py

embed: src/embed.py
	$(PYTHON) src/embed.py

translate: src/translate.py
	$(PYTHON) src/translate.py

build: src/build_site.py
	$(PYTHON) src/build_site.py

alert: src/alert_bot.py
	$(PYTHON) src/alert_bot.py

clean:
	rm -rf data/views/*

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
