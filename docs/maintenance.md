# Maintenance

Translations for website templates live under `locale/` as gettext `messages.po` files. Edit `locale/en/LC_MESSAGES/messages.po` to add new strings then update every other language.
Run `make precommit` to compile the `.po` files and verify that all languages contain every string.
