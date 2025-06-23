# Output Validation

Every step of the pipeline saves files that the next stage depends on.
Each script checks for missing pieces and exits with an error when something is wrong.

## Captions

Each image stored under `data/media` must have a matching `*.caption.json` file.
Captions include `caption_<lang>` keys for every language listed in `LANGS`.
Missing captions mean the chopper cannot pair pictures with their text.

## Lots

All message Markdown files under `data/raw` should have a JSON lot file in
`data/lots`. Without it the embedder will skip the message. Every lot must
include translated titles and descriptions for each language. Missing
translations are treated as an error and the cleanup step removes such files
so the parser can try again. Lots flagged with `fraud` are kept even when
translations are missing so questionable posts can be reviewed later.

## Vectors

Every lot JSON is expected to have an embedding stored in `data/vectors`.
A vector older than its source lot is treated as stale and reported.
Pages are not generated for lots missing embeddings so incomplete data never
reaches the website.

Earlier versions used a dedicated ``validate_outputs.py`` helper.
The checks are now built into the main pipeline stages so no additional commands are needed.
