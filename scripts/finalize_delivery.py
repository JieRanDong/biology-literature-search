#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Finalize the delivery directory — Stage 5.5 of biology-literature-search.

After the earlier stages the delivery directory holds a flat mix of papers,
scratch artifacts (merged.json, selection.json, the raw per-backend JSON) and the
workbook. This sorts them into their final places:

    <dir>/
    ├── 文献清单.xlsx          the deliverable, stays at the top level
    ├── _paper/                the downloaded papers
    │   ├── NN_<slug>.pdf
    │   ├── NN_<slug>.txt
    │   └── NN_<slug>.fulltext.xml
    └── _work/                 everything that produced the above

**Nothing is deleted.** `_work/` retains merged.json, selection.json and the raw
backend responses, so `build_report.py` can be re-run.

Papers are identified two ways: every `local_file` named in selection.json, and
any file matching the download naming convention `NN_<slug>.{pdf,txt,xml}` — the
latter is what keeps a `.fulltext.xml` companion, which selection.json does not
name, next to its `.txt`.

The script also enforces an integrity check: every `local_file` named in
selection.json must resolve to a real file. It exits 1 and lists any that are
missing — a paper marked 已下载 whose file is absent is a fabricated status.

Usage:
  uv run scripts/finalize_delivery.py --dir tmp_litsearch/run3
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

KEEP_TOP = {"文献清单.xlsx"}
PAPER_DIR = "_paper"
PAPER_RE = re.compile(r"^\d{2,}_.+\.(pdf|txt|xml)$", re.IGNORECASE)


def load_promised(directory, work_name):
    """`local_file` values from selection.json — the papers we owe the user.

    Returns paths relative to the delivery directory, e.g. `_paper/04_x.pdf`.
    Both that form and a legacy bare filename are accepted.
    """
    for candidate in (directory / "selection.json",
                      directory / work_name / "selection.json"):
        if candidate.is_file():
            try:
                sel = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                sys.exit(f"{candidate} is not valid JSON: {exc}")
            return [i["local_file"] for i in sel.get("items", []) if i.get("local_file")]
    return []


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="the delivery directory")
    ap.add_argument("--work-name", default="_work",
                    help="subdirectory for scratch artifacts (default: _work)")
    ap.add_argument("--paper-name", default=PAPER_DIR,
                    help="subdirectory for the downloaded papers (default: _paper)")
    a = ap.parse_args()

    directory = Path(a.dir)
    if not directory.is_dir():
        sys.exit(f"not a directory: {directory}")

    work = directory / a.work_name
    paper = directory / a.paper_name
    promised = load_promised(directory, a.work_name)
    promised_names = {Path(p).name for p in promised}

    if not promised:
        print("warning: no selection.json found — identifying papers by the "
              "NN_<slug> naming convention alone", file=sys.stderr)

    kept, filed, moved, conflicts = [], [], [], []
    for entry in sorted(directory.iterdir()):
        if entry.name in (a.work_name, a.paper_name):
            continue
        name = entry.name

        if name in KEEP_TOP:
            kept.append(name)
            continue

        is_paper = (name in promised_names
                    or (entry.is_file() and PAPER_RE.match(name)))
        dest_dir = paper if is_paper else work
        dest_dir.mkdir(exist_ok=True)

        target = dest_dir / name
        if target.exists():
            # Never clobber: same name twice means two runs shared a directory.
            conflicts.append(f"{name} → {dest_dir.name}/")
            continue
        shutil.move(str(entry), str(target))
        (filed if is_paper else moved).append(name)

    print(f"delivery directory: {directory}")
    print(f"  kept at top level ({len(kept)}): {', '.join(kept) or '—'}")
    print(f"  filed into {a.paper_name}/ ({len(filed)}):")
    for n in filed:
        print(f"    ▸ {n}")
    print(f"  moved into {a.work_name}/ ({len(moved)}):")
    for n in moved:
        print(f"    → {n}")
    if conflicts:
        print(f"  ! NOT moved — name already present in target ({len(conflicts)}): "
              f"{', '.join(conflicts)}", file=sys.stderr)
        print("    resolve manually; nothing was overwritten", file=sys.stderr)

    # Integrity check: selection.json promises these files exist.
    missing = sorted(p for p in promised if not (directory / p).is_file())
    if missing:
        print(f"\n!! selection.json names {len(missing)} local_file(s) that do NOT "
              f"resolve to a file:", file=sys.stderr)
        for p in missing:
            print(f"     {p}", file=sys.stderr)
        print("   Either the download never landed, or it was filed elsewhere. Fix the "
              "status/local_file in selection.json before shipping — do not leave a "
              "'已下载' claim pointing at a missing file.", file=sys.stderr)
        return 1

    print(f"\nOK — top level: 文献清单.xlsx + {a.paper_name}/ + {a.work_name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
