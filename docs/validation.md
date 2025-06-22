# Output Validation

Every step of the pipeline saves files that the next stage depends on.
Each script checks for missing pieces and exits with an error when something is wrong.

## Captions

Each image stored under `data/media` must have a matching `*.caption.md` file.
Missing captions mean the chopper cannot pair pictures with their text.

## Lots

All message Markdown files under `data/raw` should have a JSON lot file in
`data/lots`. Without it the embedder will skip the message.

## Vectors

Every lot JSON is expected to have an embedding stored in `data/vectors`.
A vector older than its source lot is treated as stale and reported.

Earlier versions used a dedicated ``validate_outputs.py`` helper.
The checks are now built into the main pipeline stages so no additional commands are needed.
