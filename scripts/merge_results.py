#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Merge and de-duplicate literature-search results from multiple backends.

Each backend returns a different shape. This normalises them into one record
type, collapses duplicates across backends, and reports per-backend overlap.

Usage:
  uv run scripts/merge_results.py --out merged.json \
    --input pubmed:tmp_litsearch/pubmed_abstracts.json \
    --input europepmc:tmp_litsearch/europepmc.json \
    --input biorxiv:tmp_litsearch/biorxiv.json

Supported backends: pubmed, europepmc, biorxiv (alias: medrxiv).

De-duplication key priority: DOI -> PMID -> normalised title.
A paper found by several backends is kept once, with `found_in` listing them all.
"""

import argparse
import json
import re
import sys
from pathlib import Path

BACKENDS = {"pubmed", "europepmc", "biorxiv", "medrxiv"}

DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                "http://dx.doi.org/", "doi:")

# Europe PMC escapes its inline JATS markup, so a title arrives as
# "&lt;i&gt;Cladocopium&lt;/i&gt;". Entities must be DECODED before tags are
# stripped, otherwise the escaped tag never matches the tag pattern and the
# literal "i" / "/i" survives into the displayed title.
ENTITY_DECODE = {
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&quot;": '"',
    "&apos;": "'",
    "&#39;": "'",
    "&nbsp;": " ",
}
_ENTITY_LEFT = re.compile(r"&[a-zA-Z]+;|&#\d+;")


def clean_text(value):
    """Decode entities, drop tags, collapse whitespace. None for empty input."""
    if not value or not isinstance(value, str):
        return None
    text = value
    for entity, char in ENTITY_DECODE.items():
        text = text.replace(entity, char)
    text = re.sub(r"<[^>]+>", " ", text)   # now real tags, post-decode
    text = _ENTITY_LEFT.sub(" ", text)     # anything still escaped
    text = " ".join(text.split())
    return text or None


def norm_doi(value):
    """Normalise a DOI to bare lowercase form, or None."""
    if not value or not isinstance(value, str):
        return None
    doi = value.strip().lower()
    for prefix in DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    doi = doi.strip()
    return doi if doi.startswith("10.") else None


def norm_title(value):
    """Collapse a title to a comparable form, or None."""
    title = clean_text(value)
    if not title:
        return None
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())  # strip punctuation
    title = " ".join(title.split())
    return title if len(title) >= 20 else None       # too short to be distinctive


def record_keys(raw):
    """Every identity a record can be matched on, strongest first.

    Matching on a single key is not enough. One backend may supply a DOI while
    another carries only the PMID for the same paper (no DOI on record), and a
    bare PMID list has no DOI at all — with one key those never collapse, and the
    merge silently returns duplicates. Register all of them.
    """
    keys = []
    if raw.get("doi"):
        keys.append(raw["doi"])
    if raw.get("pmid"):
        keys.append(f"pmid:{raw['pmid']}")
    title = norm_title(raw.get("title"))
    if title:
        keys.append(f"title:{title}")
    return keys


def first_year(*values):
    """Pull a 4-digit year out of any of the given values."""
    for value in values:
        if isinstance(value, int) and 1800 < value < 2200:
            return value
        if isinstance(value, str):
            match = re.search(r"(1[89]\d\d|20\d\d|21\d\d)", value)
            if match:
                return int(match.group(1))
    return None


def collapse_access(flags):
    """Reduce several per-backend access flags to one status."""
    flags = {f for f in flags if f}
    if "oa" in flags:
        return "OA"
    if "preprint" in flags:
        return "preprint"
    if "subscription" in flags:
        return "subscription"
    return "unknown"


def clean_authors(value):
    """Normalise authors to a list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [a.strip() for a in re.split(r"[;,]", value) if a.strip()]
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item.strip())
            elif isinstance(item, dict):
                name = (item.get("author") or {}).get("display_name") \
                    if isinstance(item.get("author"), dict) else None
                out.append(name or item.get("display_name") or item.get("name") or "")
        return [a for a in out if a]
    return []


# --------------------------------------------------------------------------
# Per-backend normalisers. Each yields dicts in the common record shape.
# --------------------------------------------------------------------------

def norm_europepmc(payload):
    for item in payload.get("results", []) if isinstance(payload, dict) else []:
        is_oa = str(item.get("isOpenAccess", "")).upper() == "Y"
        yield {
            "doi": norm_doi(item.get("doi")),
            "pmid": item.get("pmid"),
            "pmcid": item.get("pmcid"),
            "title": clean_text(item.get("title")),
            "year": first_year(item.get("pubYear")),
            "journal": clean_text(item.get("journalTitle")),
            "authors": clean_authors(item.get("authorString")),
            "abstract": clean_text(item.get("abstractText")),
            "url": f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}"
                   if item.get("id") else None,
            "access": "oa" if is_oa else "subscription",
            "cited_by": item.get("citedByCount"),
            "oa_status": "open access" if is_oa else None,
        }


def norm_pubmed(payload):
    # search_pubmed emits a bare list of PMID strings; fetch_article_abstracts
    # emits a list of objects. Handle both.
    if not isinstance(payload, list):
        return
    for item in payload:
        if isinstance(item, str):
            yield {"doi": None, "pmid": item, "pmcid": None, "title": None,
                   "year": None, "journal": None, "authors": [], "abstract": None,
                   "url": f"https://pubmed.ncbi.nlm.nih.gov/{item}/",
                   "access": None, "cited_by": None, "oa_status": None}
            continue
        pmid = item.get("pmid")
        yield {
            "doi": norm_doi(item.get("doi")),
            "pmid": pmid,
            "pmcid": None,
            "title": clean_text(item.get("title")),
            "year": first_year(item.get("pubdate")),
            "journal": clean_text(item.get("journal")),
            "authors": clean_authors(item.get("authors")),
            "abstract": clean_text(item.get("abstract")),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            "access": None,  # PubMed records don't carry an OA flag
            "cited_by": None,
            "oa_status": None,
        }


def norm_biorxiv(payload):
    # search_by_dates.py emits a JSON array; search_by_doi.py emits a SINGLE
    # object. Accept both — handling only the array silently drops every
    # DOI-resolved record, which is this backend's most reliable entry point.
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        published = item.get("published")
        yield {
            "doi": norm_doi(item.get("doi")),
            "pmid": None,
            "pmcid": None,
            "title": clean_text(item.get("title")),
            "year": first_year(item.get("date")),
            "journal": clean_text(item.get("server")) or "bioRxiv",
            "authors": clean_authors(item.get("authors")),
            "abstract": clean_text(item.get("abstract")),
            "url": f"https://doi.org/{norm_doi(item.get('doi'))}" if norm_doi(item.get("doi")) else None,
            "access": "preprint",
            "cited_by": None,
            "oa_status": "preprint",
            "published_as": published if isinstance(published, str) and published not in ("NA", "") else None,
            "category": item.get("category"),
        }


NORMALISERS = {
    "europepmc": norm_europepmc,
    "pubmed": norm_pubmed,
    "biorxiv": norm_biorxiv,
    "medrxiv": norm_biorxiv,
}


def load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        sys.exit(f"Error: input file not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: {path} is not valid JSON ({exc}). "
                 f"If this is a backend that writes to stdout, did you redirect it to a file?")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="merged JSON output path")
    parser.add_argument("--input", action="append", default=[], metavar="BACKEND:PATH",
                        help="repeatable; BACKEND is one of " + ", ".join(sorted(BACKENDS)))
    parser.add_argument("--pretty", action="store_true", help="indent the output JSON")
    args = parser.parse_args()

    if not args.input:
        sys.exit("Error: at least one --input BACKEND:PATH is required")

    records = {}   # primary key -> record
    alias = {}     # any identity -> primary key
    order = []
    per_backend = {}

    for spec in args.input:
        if ":" not in spec:
            sys.exit(f"Error: --input must be BACKEND:PATH, got {spec!r}")
        backend, _, path = spec.partition(":")
        backend = backend.strip().lower()
        if backend not in NORMALISERS:
            sys.exit(f"Error: unknown backend {backend!r}. Known: {sorted(BACKENDS)}")

        payload = load(path)
        count = 0
        for raw in NORMALISERS[backend](payload):
            count += 1
            candidates = record_keys(raw)
            if not candidates:
                continue  # nothing to dedup on and not enough metadata to be useful

            key = None
            for candidate in candidates:
                if candidate in alias:
                    key = alias[candidate]
                    break
                if candidate in records:
                    key = candidate
                    break

            if key is None:
                key = candidates[0]
                raw["found_in"] = [backend]
                raw["access_flags"] = [raw.get("access")]
                records[key] = raw
                order.append(key)
            else:
                existing = records[key]
                if backend not in existing["found_in"]:
                    existing["found_in"].append(backend)
                existing["access_flags"].append(raw.get("access"))
                # fill gaps without overwriting what we already have
                for field in ("doi", "pmid", "pmcid", "title", "year", "journal",
                              "abstract", "url", "cited_by", "oa_status", "published_as",
                              "category"):
                    if not existing.get(field) and raw.get(field):
                        existing[field] = raw[field]
                if not existing.get("authors") and raw.get("authors"):
                    existing["authors"] = raw["authors"]

            # Remember every identity, so a later record can match on any of them.
            for candidate in candidates:
                alias.setdefault(candidate, key)

        if count == 0:
            print(
                f"Warning: the {backend} input {path} produced 0 records. Either the "
                f"file is empty, or it is not this backend's output shape — a silent "
                f"zero here means that backend contributed nothing to the merge.",
                file=sys.stderr,
            )
        per_backend[backend] = {"path": path, "records_read": count}

    merged = []
    for key in order:
        record = records.pop(key)
        record["access"] = collapse_access(record.pop("access_flags", []))
        record["key"] = key
        merged.append(record)

    merged.sort(key=lambda r: (r.get("year") or 0), reverse=True)

    multi = [r for r in merged if len(r["found_in"]) > 1]
    stats = {
        "backends": per_backend,
        "unique_records": len(merged),
        "found_by_multiple_backends": len(multi),
        "by_access": {},
        "note": "Backends that only returned bare PMIDs carry no title/abstract; "
                "run the backend's abstract fetch to enrich them before merging.",
    }
    for record in merged:
        stats["by_access"][record["access"]] = stats["by_access"].get(record["access"], 0) + 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"stats": stats, "records": merged}, handle,
                  ensure_ascii=False, indent=2 if args.pretty else None)

    print(json.dumps(stats, indent=2), file=sys.stderr)
    print(f"Wrote {len(merged)} unique records to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
