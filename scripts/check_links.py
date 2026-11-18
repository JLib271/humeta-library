"""Check the library's links to other sites (McMurry et al. 2017, lesson 10: monitor outbound references).

    python scripts/check_links.py                 # print the links that fail
    python scripts/check_links.py --report FILE   # also write a Markdown report (for the monthly issue)

Follows every web address and DOI in the library's records. A link that fails twice in a row
(on separate checks) should be fixed, replaced with a persistent identifier, or marked obsolete.
Exit code 0 = every link works, 1 = some failed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_archive import archive_paths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
SKIP = ("https://w3id.org/humeta",)  # HuMeta's own identifiers resolve to this site
HEADERS = {"User-Agent": "HuMeta-link-check (https://github.com/JLib271/humeta-library)"}


def links(library: Path = REPO) -> dict[str, set[str]]:
    """Every outbound link in the library's records: URL -> the files that use it."""
    found: dict[str, set[str]] = {}

    def walk(node, key, where):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k, where)
        elif isinstance(node, list):
            for v in node:
                walk(v, key, where)
        elif isinstance(node, str):
            url = None
            if node.startswith(("http://", "https://")) and " " not in node:
                url = node
            elif key == "doi" and DOI.match(node):
                url = "https://doi.org/" + node
            if url and not url.startswith(SKIP):
                found.setdefault(url, set()).add(where)

    for path in archive_paths(library):
        if path.suffix == ".json" and "schema" not in path.parts:
            walk(json.loads(path.read_text(encoding="utf-8")), None, path.relative_to(library).as_posix())
    return found


def status(url: str, timeout: float = 20) -> str | None:
    """None if the link works, else what went wrong. Tries HEAD, then GET (some sites refuse HEAD)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=HEADERS), timeout=timeout):
            return None
    except Exception:  # noqa: BLE001 - fall through to GET
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout):
            return None
    except urllib.error.HTTPError as e:
        # Refused or rate-limited (401, 403, 429) is a site turning away robots, not a missing record
        return None if e.code in (401, 403, 429) else f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - DNS, TLS, timeouts
        return type(e).__name__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="write a Markdown report here")
    args = ap.parse_args(argv)
    found = links()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(zip(found, pool.map(status, found)))
    broken = {u: s for u, s in results.items() if s}
    print(f"Checked {len(found)} links: {len(broken)} failed.")
    lines = []
    for url, why in sorted(broken.items()):
        where = ", ".join(sorted(found[url]))
        print(f"  {why:<16} {url}  ({where})")
        lines.append(f"- [ ] {url} ({why}), in {where}")
    if args.report:
        args.report.write_text(
            "The monthly link check could not reach these links in the library's records. For each one, "
            "fix it, replace it with a persistent identifier (such as a DOI), or mark it obsolete. "
            "See IDENTIFIERS.md, \"Links to other sites\".\n\n" + ("\n".join(lines) or "Every link worked.") + "\n",
            encoding="utf-8")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
