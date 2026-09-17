# Measured coverage — what each backend actually sees

These numbers were measured on 2026-09-17 against the live APIs. They are the
evidence behind the routing decisions in `SKILL.md`. Re-measure if a backend's
behaviour is ever in doubt; the commands are given at the bottom.

## Europe PMC discards half its own corpus by default

| Topic | skill default (OA-only) | full corpus | Retained |
|---|---|---|---|
| zoology | 93,136 | 219,467 | 42% |
| ecology | 291,091 | 673,934 | 43% |
| evolutionary biology | 280,923 | 459,444 | 61% |
| plant biology | 314,140 | 606,089 | 52% |
| cell biology | 1,328,926 | 2,769,901 | 48% |

**Caveats — read these before quoting the table.**

- This is a *filter* problem, not a scope problem. Europe PMC genuinely covers
  organismal biology (zoology, ecology, plant science), not just biomedicine —
  which is why it earns the primary-sweep role once the filter is bypassed.
- Hit counts measure corpus breadth, **not relevance ranking quality**. PubMed's
  ranking for a well-formed MeSH query is usually better than a bare full-text
  search despite its smaller absolute count — that is why both sweeps run.
- A corpus count is not a result count. Never report a `hitCount` as the number of
  papers you found.

## What each backend is the only source of

| Capability | Only backend that has it |
|---|---|
| Curated paper→gene/protein/nucleotide/PubChem links | PubMed |
| MeSH-controlled vocabulary, `[Organism]`, proximity search | PubMed |
| Readable full text and PDFs | Europe PMC (then PubMed PMC) |
| Citation graph (citing + references) | Europe PMC |
| Brand-new biology preprints, by subject category | bioRxiv / medRxiv |

## What each backend misses

- **PubMed** — MEDLINE-indexed journals only. Preprints, books, pure taxonomy,
  systematics and some field-ecology journals are not indexed. Full text is
  restricted to the PMC OA subset. Citation links lag publication by 4–8 weeks, so
  a recent paper legitimately returns `[]`.
- **Europe PMC** — its stock skill discards 39–58% of its own corpus via
  `OPEN_ACCESS:y` (bypassed here — see `SKILL.md`). Full-text *retrieval* still
  needs the paper to be in the OA subset; discovering it does not.
- **bioRxiv / medRxiv** — preprints only, never peer-reviewed, and not searchable by
  keyword server-side. No PDF download. Nothing published before its date window.

## Choosing backends for a request

- **"Find everything on <topic>"** → both PubMed and Europe PMC. This is the case
  that motivated this skill; a single backend provably cannot do it.
- **"Is this organism/clade well studied?"** → Europe PMC broad + PubMed MeSH.
  Ecology and taxonomy topics lean Europe PMC/bioRxiv; molecular and clinical lean
  PubMed.
- **"Which genes/proteins does this literature implicate?"** → PubMed, via
  `find_linked_biological_data`. No other backend here answers that.
- **"What came out this month?"** → bioRxiv (preprints) + Europe PMC `FIRST_PDATE:`
  (what has since been published).
- **"I need to read these"** → Europe PMC full text/PDF; expect only the OA subset.

## Not covered

Cross-disciplinary breadth, funding and institution analytics, and authors or works
outside the life sciences are **not** answerable by the backends wired into this
skill. Those are the job of `literature-search-openalex` used on its own, which is
excluded here because its CLI needs an OpenAlex API key to be usable.

## Re-measuring

```bash
# Europe PMC, OA-only vs full corpus
for q in zoology ecology; do
  for suffix in " AND OPEN_ACCESS:y" " AND (OPEN_ACCESS:y OR OPEN_ACCESS:n)"; do
    curl -s -m 25 --get --data-urlencode "query=($q)$suffix" \
      --data-urlencode "format=json" --data-urlencode "pageSize=1" \
      "https://www.ebi.ac.uk/europepmc/webservices/rest/search" \
      | python -c "import sys,json;print('$q$suffix ->',json.load(sys.stdin)['hitCount'])"
  done
done
```

Note: these are diagnostic probes for re-validating the table, not the normal
retrieval path — normal use goes through the backend wrapper scripts, which own the
rate limiting.
