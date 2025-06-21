# Ontology Housekeeping

The parser stores counts of all fields and values under `data/ontology`.
These files help refine prompts and keep the database consistent.

## Updating the files

Run the ontology scanner after chopping lots:

```bash
make ontology
```

Do not run this command if you only have the repository without the original
`data/raw` posts. The script would overwrite the tracked JSON files with empty
data. In that case simply inspect the existing files under `data/ontology`.

The command writes several JSON files under `data/ontology`:

- `fields.json` – all keys with value counts.
- `misparsed.json` – lots that failed validation together with the input
  text passed to the parser.
- `fraud.json` – lots explicitly flagged with a `fraud` tag and the text
  that produced them.
- `broken_meta.json` – references to messages that need refetching.
- `title_*.json` and `description_*.json` – unique values per language for
  manual review.

Commit the updated JSON files to the repository whenever the data is
re-parsed so the history reflects changes to the schema.

## Reviewing `fields.json`

Look for unexpected keys or obvious duplicates. Adjust
`prompts/chopper_prompt.md` when you notice new patterns so the model keeps
producing clean JSON. When counts suggest a field is rarely used, consider
removing it from the prompt to save tokens.

## Reviewing `misparsed.json`

Misparsed lots include the exact text that produced them under the `input`
key. Inspect a few entries to see why the model struggled. Tweak the prompts
or parsing code to handle those cases. Once the issues are resolved remove
the entries and regenerate the file.

## Titles and Descriptions

The chopper generates `title_<lang>` and `description_<lang>` for every lot.
They should summarise the offer clearly. Popular boilerplate titles or
descriptions that do not distinguish one ad from another should be
explicitly discouraged in the prompt so the resulting website lists are
useful.

## Photo Captions

The captioning prompt in `prompts/captioner_prompt.md` influences what
attributes the chopper can infer. Update it when you see new property
features or room details appear in `fields.json` so captions mention them
explicitly. This helps the parser extract attributes like `view`, `heating`
or notable furniture from the images.
