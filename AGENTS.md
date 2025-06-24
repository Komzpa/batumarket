# Important rules for agents

Documentation:
 - Check out README.md.
 - Check data schema as described in `docs/`.
 - docs/ folder has general project documentation that needs to be kept up to date.
 - Fix everything in the `docs/` folder to match reality.
 - Don't update `README.md` with minor code fixes.
 - When moving around md files also fix the links in them and links to them across all others.
 - Prefer storing notes and documentation as markdown (``.md``).
 - Update docs every time you update something significant across files.

Debugging:
 - Write enough comments so you can deduce what was a requirement in the future and not walk in circles.
 - Add enough debug logs so you can find out what's wrong but not be overwhelmed when something does not work as expected.
 - Use TDD if change is not trivial: start by designing solution/docs, then write tests, then change code to do the thing it should.
 - Use TDD to handle bugs.
 - Code test coverage is measured by codecov. Write useful tests to increase it and check key requirements to hold.
 - When refactoring to move a feature, don't forget to remove the original code path.
 - Don't stub stuff out with insane fallbacks (like lat/lon=0) - instead make the rest of the code work around data absence and inform user.
 - File names may have spaces in them, check that you are correctly quoting and escaping them.
 - When adding logs, add message before starting something as long as after finishing, as it will let you find what crashed in the middle.
 - Inject data assertions into IO abstraction libraries to catch any data that violates them.
 - Use docs/todo.md as to put issues, inconveniences and impediments that you noticed that you are not fixing on this iteration.

Style:
 - Add empty lines between logical blocks as in the rest of the codebase.
 - Start sentences at new lines in docs for cleaner git diffs.
 - Clean stuff up if you can: fix typos, make lexics more correct in English.
 - Write insightful code comments.
 - Do not break indentation.
 - Do not mix tabs and spaces.
 - Format the code nicely and consistently.
 - Do not replace URLs with non-existing ones.
 - If a file with code grows longer than 500 lines, refactor it into two or move some parts into already created libraries.
 - Every feature needs to have comprehensive up-to-date documentation near it, write it.

Java:
 - Write enough comments so that people proficient in Python, PostGIS can grasp the Java code.
 - Just ignoring exceptions is not the best fix, handle in a better way

SQL:
 - prefer indexed operators when dealing with jsonb ( `tags @> '{"key": "value"}` instead of `tags ->> 'key' = 'value'` ).
 - SQL is lowercase, PostGIS functions follow their spelling from the manual (`st_segmentize` -> `ST_Segmentize`).
 - values in layers should be absolute as much as possible: store "birthday" or "construction date" instead of "age".
 - SQL files should to be idempotent: drop table if exists; add some comments to make people grasp quereies faster.
 - Format queries in a way so it's easy to copy them out of the codebase and debug standalone.

Make:
 - Makefile: If you need intermediate result from other target, split it into two and depend on the intermediate result.
 - Makefile: there are comments on the same line after each target separated by ## - they are used in debug graph visualization, need to be concise and descriptive of what's going on in the code itself.
 - Trivial oneliner SQLs are okay to keep in Makefile.
 - Format target comments as self-documented Makefile, on same line: `target: dependencies | order_only_deps ## Description`
 - Remember than Makefile uses tabs.
 - Explain high-level architecture and quirks in Makefile
 - To smoke-check Makefile, `make --trace all` helps see dependency chain.

Python:
 - Write comments for each logical block.

AI:
 - Try to make a patch to fix/improve things even if user's request sounds like a question.
 - Check token counts.
 - Use system prompts where needed.
 - Colloquial "vectors" are to be called "embeddings" in codebase.

Testing:
 - Github Actions is used as CI. Update it as necessary.
 - Use `make precommit` to run the checks. This sorts files, verifies Makefile tabs and compiles all Python code via `scripts/check_python.sh`.
 - To run the pipeline in testing offline mode, launch `TEST_MODE=1 PYTHONPATH=. make -B -j all` and check if everything works as intended.
 - For any fix you are implementing try to add test so that it won't repeat in the future.

Pull requests:
 - Use Conventional Commits convention when formatting the pull request and commits, e.g. `type(scope): TICKETNUMBER title ...`. Skip ticket number if not provided. Field: Public Id.
