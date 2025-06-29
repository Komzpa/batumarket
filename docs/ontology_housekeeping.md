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
- `fields.approved.json` – curated field descriptions with sample values.
  Each entry includes a `key`, `description_en` and a list of common `values`.
- `misparsed.json` – lots that failed validation together with the input
  text passed to the parser.
- `fraud.json` – lots explicitly flagged with a `fraud` tag and the text
  that produced them.
- `broken_meta.json` – references to messages that need refetching.
- `misparsed.json` – lots that looked suspicious. Updating the file causes the
  corresponding JSON lots to be dropped so they will be parsed again.
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
key. Inspect a few entries to see why the model struggled. Posts without a
timestamp or any seller information also end up here so they can be reviewed.
Raw posts missing contact details or a timestamp are treated the same.  The
helper functions in `lot_io.py` and `post_io.py` determine the seller and
validate timestamps so both the ontology scan and website stay in agreement.
Tweak the prompts or parsing code to handle those cases. Once the issues are
resolved remove the entries and regenerate the file.

## Titles and Descriptions

The chopper generates `title_<lang>` and `description_<lang>` for every lot.
Every language version must be present. The lot serializer rejects JSON
files missing any of them and the cleanup step drops such entries so the
parser can try again. Lots marked with `fraud` are exempt from this rule so
evidence of scams is not lost during maintenance.
Titles and descriptions should summarise the offer clearly. Popular
boilerplate text that does not distinguish one ad from another should be
explicitly discouraged in the prompt so the resulting website lists are
useful.

## Photo Captions

The captioning prompt in `prompts/captioner_prompt.md` influences what
attributes the chopper can infer. Update it when you see new property
features or room details appear in `fields.json` so captions mention them
explicitly. The prompt now stresses qualities a buyer cares about and asks the
model to skip "This image..." style preambles. This helps the parser extract
attributes like `view`, `heating` or notable furniture from the images.
