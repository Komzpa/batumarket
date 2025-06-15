Remember than Makefile uses tabs
When refactoring to move feature don't forget to remove original code path
Adjust something .gitignore accordingly
Write insightful code comments
Check token counts
Add enough debug logs so you will be able to find out what's wrong but not be overwhelmed when something does not work as expected
Use system prompts where needed
Try to make a patch to fix/improve things even if user's request sounds like a question
Explain high-level architecture and quirks in makefile
Write enough comments so you can deduce what was a requirement in the future
Don't stub stuff out with insane fallbacks (like lat/lon=0) - instead make the rest of the code work around data absence and inform user
Postgres \copy has to be on single line to work
When moving around md files also fix the links in them and links to them across all others
File names are with spaces in them, check that you are correctly quoting and escaping them
Update docs every time you update someting significant across files
Prefer storing notes and documentation as markdown (``.md``). If in doubt,
Default to ``.md`` over ``.txt`` so links and headers work consistently.
Fix everything in docs/ folder to match reality
Use `make -f src/Makefile precommit` to run the checks. This sorts files, verifies Makefile tabs and compiles all Python code via `scripts/check_python.sh`.
To run the pipeline in testing offline mode, launch `TEST_MODE=1 PYTHONPATH=. make -B -j -f src/Makefile compose` and check if everything works as intended.
To smoke-check Makefile, `make --trace -f src/Makefile compose` helps see dependency chain.
