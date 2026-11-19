# HuMeta identifier policy

HuMeta gives every record in the HuMeta Instrument Library a persistent identifier: every
instrument, instrument version, item, shared construct, and theory or framework. This page
says what the identifiers look like, what they promise, and how to cite them.

**Status:** adopted November 2026. The identifiers start resolving once w3id.org accepts the
`/humeta/` registration (pending). Until the library's identifier work is merged, some files this
page links to (`identifiers.csv`, the redirect rules) are not on the main branch yet.

The policy follows the ten lessons in McMurry, J. A., et al. (2017). Identifiers for the 21st
century: How to design, provision, and reuse persistent identifiers to maximize utility and
impact of life science data. *PLOS Biology*, 15(6), e2001414.
<https://doi.org/10.1371/journal.pbio.2001414>. The table at the end shows how HuMeta
follows each lesson.

## What the identifiers look like

| Record | Local ID pattern | Example | Persistent URI | Compact form |
|---|---|---|---|---|
| Instrument | `^hmi[0-9]{4}$` | `hmi0004` | `https://w3id.org/humeta/instrument/hmi0004` | `humeta.instrument:hmi0004` |
| Instrument version | `^hmi[0-9]{4}\.[1-9][0-9]*$` | `hmi0004.1` | `https://w3id.org/humeta/instrument/hmi0004.1` | `humeta.instrument:hmi0004.1` |
| Item | `^[a-z0-9]+(-[a-z0-9]+)*$`, within its instrument | `q05` | `https://w3id.org/humeta/instrument/hmi0004/item/q05` | |
| Shared construct | `^hmc[0-9]{4}$` | `hmc0024` | `https://w3id.org/humeta/construct/hmc0024` | `humeta.construct:hmc0024` |
| Theory or framework | `^hmf[0-9]{4}$` | `hmf0038` | `https://w3id.org/humeta/framework/hmf0038` | `humeta.framework:hmf0038` |

The URI pattern for each type is `https://w3id.org/humeta/<type>/$id`, where `$id` is the
local ID exactly as written above. The compact form is `<prefix>:<local ID>`, and the prefix
stands for that URI pattern, so either form gives the other.

The scheme URIs `https://w3id.org/humeta/instrument`, `.../construct` and `.../framework` name
the lists of records, and `https://w3id.org/humeta/metadata-code` names the HuMeta metadata-code
scheme (Construct_Measure_Item_Target).

Each record has one address on the library's website, named by its identifier
(`https://jlib271.github.io/humeta-library/instruments/hmi0004/`), and its data files are named
the same way (`data/instruments/hmi0004.json`). There are no name-based copies.

The identifiers resolve through [w3id.org](https://w3id.org/), a community-run redirect
service. The redirect rules are in [`w3id/ids/humeta/.htaccess`](w3id/ids/humeta/.htaccess). If
the library's website moves, only the redirect changes; the identifiers do not.

## Identifiers carry no meaning

An identifier tells you what type of record it is (`i`, `c` or `f`) and nothing else. It does
not contain a name, an acronym, an author, or a year, because all of those can change or
collide: acronyms are shared across fields, instruments and constructs are renamed (the
construct-naming committee can rename a construct), and two instruments can share a lead
author and year. Numbers are issued in sequence and say nothing about the record.

Use the record's **name** to read it and its **identifier** to refer to it. Instruments also
have a HuMeta **metadata code** (for example `Libarkin2005V4`) that HuMeta uses in variable
names; it is a readable label, not an identifier, and it is never relied on for uniqueness.

Item IDs are the one partial exception: an item's ID is fixed when the item is first added to
the library, usually from its number in the first version that has it (`q05`). It is never
renumbered, so in later versions the item's number and its ID can differ. Each version's item
number is recorded separately.

## Versions

An instrument identifier (`hmi0004`) names the instrument as a whole, across all its versions.
A version identifier adds a dot and HuMeta's version number: `hmi0004.1` is the first version of
that instrument added to the library, `hmi0004.2` the second, and so on. **The number is
HuMeta's, not the publisher's**: the Geoscience Concept Inventory's version 4 is `hmi0004.1`
because it was the first GCI version in the library. The publisher's version name is in the
version's label and in its metadata code (`Libarkin2005V4`).

A version is a different set or wording of items (a revision, a translation, an adaptation).
Corrections to a record's description do not create a new version; they are kept in the
library's history (every change is a Git commit) and in dated **releases**: each release of the
whole library is archived with its own DOI, so any earlier state can be cited and retrieved.
See [Releases](README.md#releases).

Items keep the same ID in every version where they are unchanged. A changed item gets a new
ID and a link to the item it came from (see [Items across versions](README.md#items-across-versions)).

## Identifiers are never reassigned or deleted

Once issued, an identifier always means the same record.

- Every identifier ever issued is listed in [`identifiers.csv`](identifiers.csv), with its
  type, the record it was issued to, the date, and its status (`active` or `retired`).
- The library's validator fails if an identifier is missing from the library, is given to a
  different record, or is used twice. Numbers are never reused, even for retired records.
- A record that should no longer be used is **retired**, not deleted. A retired construct keeps
  its page, which says it is retired, when, and what to use instead. It no longer appears in
  the library's lists, but its identifier still resolves, so studies that used it can still be
  read.
- If two records turn out to be the same, one is retired and points to the other. If one
  record must be split, the original is retired and the new records get new identifiers.

## Issuing identifiers

Maintainers issue identifiers when they add records:

```
python scripts/assign_identifiers.py
```

It gives the next free identifier to each new instrument, version, construct, and theory, and
records it in `identifiers.csv`. Contributors do not choose identifiers. The portal's "own
framework" and "exploratory" choices are options, not records, and have no identifier.

## Identifiers from elsewhere

HuMeta creates identifiers only for what it describes itself. Where a record already has an
identifier elsewhere, HuMeta records that one exactly as issued and links to it through its
resolver: an instrument's DOI and its entries in registries such as APA PsycTests, ERIC,
PhysPort or CHIRAL; the DOIs of the publications that report validity evidence; a construct's
ERIC or ICPSR thesaurus term. HuMeta's own identifier does not replace them.

## Getting a record as data

Each identifier resolves to the record's web page. An instrument identifier requested with the
header `Accept: application/json` returns the instrument's library record as JSON instead:

```
curl -L -H "Accept: application/json" https://w3id.org/humeta/instrument/hmi0004
```

Each instrument page also links its schema.org and DataCite descriptions, which carry the
identifier. The whole library is downloadable as data from the website and from each release.

## How to cite

Cite a record with its identifier, not with the address in your browser's address bar. Every
record page shows its identifier with a copy button and a ready-made citation, for example:

> Geoscience Concept Inventory (GCI). HuMeta Instrument Library record hmi0004, release
> v2026.12.01. https://w3id.org/humeta/instrument/hmi0004. Accessed 2026-12-05.

To cite the library as a whole, use its release DOI (see [`CITATION.cff`](CITATION.cff)). In
codebooks and DDI files, the HuMeta Portal names instruments, versions, items, and constructs by
their identifiers.

## Links to other sites

The library's pages mark links to other sites and open them in a new tab. External records are
linked through their persistent identifiers (for example `https://doi.org/...`), not through
addresses that can change. Once a month, a check follows every external link in the library;
links that fail are listed in a GitHub issue so a maintainer can fix them or mark them
obsolete.

## How HuMeta follows the ten lessons

| Lesson (McMurry et al. 2017) | How HuMeta follows it |
|---|---|
| 1. Credit any derived content using its original identifier | Instruments, evidence and constructs keep the identifiers they already have (DOIs, PsycTests, ERIC, PhysPort, CHIRAL, thesaurus terms), exactly as issued. HuMeta issues identifiers only for its own records. |
| 2. Help local IDs travel well: document prefix and patterns | One prefix per type (`humeta.instrument`, `humeta.construct`, `humeta.framework`), each bound to one URI pattern and one regular expression, documented here. |
| 3. Opt for simple, durable web resolution | Resolution through w3id.org, a community-run resolver. URIs have no file extensions, query strings or technology names, and at most one level below the type. |
| 4. Avoid embedding meaning or relying on it for uniqueness | Local IDs are a type letter and a sequence number. Names, acronyms and metadata codes are labels, not identifiers. |
| 5. Design new identifiers for diverse uses by others | Lower-case ASCII letters and digits, one fixed pattern per type, no characters that need escaping; the dot appears only before a version number. |
| 6. Implement a version-management policy | Version identifiers with a dot (`hmi0004.1`); unchanged items keep their ID across versions; every change is in Git history and in dated, archived releases. |
| 7. Do not reassign or delete identifiers | `identifiers.csv` records every identifier issued; the validator fails if one disappears or moves; retired records keep a page saying what replaces them. |
| 8. Make URIs clear and findable | Every record page shows its identifier prominently, with a copy button, its compact form, and a citation that includes the release and access date. |
| 9. Document the identifiers you issue and use | This page, linked from every record page, the repository README and the website's About page. |
| 10. Reference and display responsibly | External links go through their resolvers, are marked, and open in a new tab; a monthly check reports broken links. |
