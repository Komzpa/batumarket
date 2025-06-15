PYTHON=python

update: pull chop caption embed translate build

pull: tg_bot.py
	$(PYTHON) src/tg_bot.py

caption: caption.py
	$(PYTHON) src/caption.py

chop: chop.py
	$(PYTHON) src/chop.py

embed: embed.py
	$(PYTHON) src/embed.py

translate: translate.py
	$(PYTHON) src/translate.py

build: build_site.py
	$(PYTHON) src/build_site.py

alert: alert_bot.py
	$(PYTHON) src/alert_bot.py

clean:
	rm -rf data/views/*

precommit:
	@find src -name '*.py' -print0 | xargs -0 scripts/check_python.sh
