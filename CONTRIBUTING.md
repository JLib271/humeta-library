# Contributing to the HuMeta Instrument Library

This repository holds the library's records and the community's recommendations. You don't need to
know anything about the HuMeta Portal's code to contribute.

## Recommending something (no GitHub needed)

- **In the HuMeta Portal:** Module 2 (Framework and Measures) → the **Recommend** tabs. Your
  recommendation arrives here as a pull request that adds one file to `suggestions/`.
- **On the website:** the [Recommend page](https://jlib271.github.io/humeta-library/recommend/)
  explains how to deposit an instrument on Knowledge Commons and links to the forms.
- **On GitHub:** the [issue forms](https://github.com/JLib271/humeta-library/issues/new/choose)
  for an instrument, a theory or framework, or a correction. When an instrument recommendation links
  a Knowledge Commons deposit, a workflow checks the deposit and comments on the issue.

Recommendations are public from the moment they are submitted.

## Reviewing a recommendation

Follow [suggestions/README.md](suggestions/README.md): check the source, leave mappings
`provisional` until the governance committee decides them, respect item-text licenses, and add the
record to the library in the same or a follow-up pull request.

## Editing records

1. Copy an existing record as a template, and fill it from the primary publication (see the
   [README](README.md#contributing)).
2. Validate:

   ```bash
   pip install -r requirements.txt
   python scripts/validate_library.py
   ```

   The validator downloads the HuMeta profile's vocabularies to check terms such as disciplines.
   Offline, pass a local copy with `--vocabularies path/to/vocabularies.json`.
3. To preview the website, clone the [HuMeta Portal](https://github.com/JLib271/HuMeta) next to this
   repository (its reader turns records into pages), then:

   ```bash
   python scripts/build_site.py      # writes _site/; open _site/index.html
   python -m pytest
   ```

4. Open a pull request. The **Check** workflow validates the records, builds the website, and runs
   the tests.

## What happens after a merge

Merging to `main` rebuilds the [website](https://jlib271.github.io/humeta-library/), which also
publishes the library's files as `data/library.tar.gz`. The HuMeta Portal reads that file, so the
change appears in the portal within a day, with no change to the portal itself.

## Decisions

Larger changes (the record format, the construct vocabulary, the evidence rubric) are proposed in an
issue labeled `proposal` and left open for comment for at least 14 days. Which instruments map to
which constructs is decided by the HuMeta governance committee; see
[GOVERNANCE.md](https://github.com/JLib271/HuMeta/blob/main/GOVERNANCE.md).

Never include item text from restricted instruments, participant data, or unpublished results.
