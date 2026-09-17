---
name: biology-literature-search
description: >
  Comprehensive literature search across ALL of biology — ecology, evolution,
  zoology, plant science, microbiology, molecular and cell biology, neuroscience,
  genomics, taxonomy — covering both preprints and published journals. Orchestrates
  three backends (PubMed/MEDLINE, Europe PMC, bioRxiv/medRxiv) to work around the
  coverage gap of any single one, then merges and de-duplicates the results into
  one access-annotated list. Use when the user wants to search biology literature
  broadly, survey a biological topic, find papers across all biology-related
  journals, or track down every relevant paper rather than querying one database.
  Trigger on: 检索生物类论文, 生物学文献, 文献检索, 综述某个生物学主题,
  biology literature search, find papers on <organism/topic>.
---

# Biology Literature Search (orchestrator)

This skill is an **orchestrator**. It does not replace the three backend skills —
it routes across them, because no single one covers biology.

**This skill ships no copies of the backend scripts.** It invokes them in place,
by absolute path, exactly as their own `SKILL.md` files document. The backend
skills are never modified.

## Backends and their jobs

| Backend | Job | Scope | Read the backend's own docs |
|---|---|---|---|
| **Europe PMC** | Primary broad sweep + full text + citation graph | Life sciences, 43M abstracts / 9M full texts, richest query syntax | `~/.claude/skills/literature-search-europepmc/` |
| **PubMed** | MEDLINE coverage + cross-database links | MEDLINE, no OA restriction, links papers to gene/protein/nucleotide/PubChem records | `~/.claude/skills/pubmed-database/` |
| **bioRxiv / medRxiv** | Fresh preprints by category | bioRxiv (27 biology categories) + medRxiv, **preprints only** | `~/.claude/skills/literature-search-biorxiv/` |

Deliberately **not** wired in: `literature-search-openalex` (its CLI 429s on this
machine without an API key — it sleeps ≥180 s per retry and reads as a hang) and
`literature-search-arxiv` (its biology coverage is only the `q-bio` sliver). Add
either back manually if the user supplies an OpenAlex key or asks for
quantitative-biology preprints.

## Why orchestrate: the measured coverage gap

Europe PMC on the same biology topics — what its stock skill returns versus what
the corpus actually holds:

| Topic | Europe PMC (skill default, OA-only) | Europe PMC (full corpus) | Retained |
|---|---|---|---|
| zoology | 93,136 | 219,467 | 42% |
| ecology | 291,091 | 673,934 | 43% |
| evolutionary biology | 280,923 | 459,444 | 61% |
| plant biology | 314,140 | 606,089 | 52% |
| cell biology | 1,328,926 | 2,769,901 | 48% |

Two conclusions drive the design:

1. **Europe PMC's stock skill sees only 42–61% of its own corpus**, because
   `europepmc_api.py:141` force-appends `OPEN_ACCESS:y`. See *Europe PMC OA policy*
   below. Europe PMC's *scope* is fine — it genuinely covers organismal biology,
   not just biomedicine. Its default *filter* is the problem.
2. **The three backends miss different things**, so the sweep needs more than one:

   | Backend | Blind to | Covered by |
   |---|---|---|
   | Europe PMC | non-OA full text (readable text only) | PubMed abstracts |
   | PubMed | preprints; books; systematic-biology journals never indexed by MEDLINE; 4–8 week citation-link lag | bioRxiv (preprints), Europe PMC (broader life-science corpus) |
   | bioRxiv | anything published before its date window; server-side keyword search does not exist | the other two, by DOI |

## Core rules

- **Never modify the backend skills.** Read them, call their scripts, change nothing.
  If one needs different behaviour, express it in the query string, not in their code.
- **Always use each backend's own wrapper script.** Never hand-roll `curl` against
  these APIs — the wrappers own the rate limiting.
- **Work in a scratch directory**, never scattered across the workspace. Use
  `./tmp_litsearch/` inside the current directory, or a path the user names.
  🔴 Name the paths and confirm before creating them.
- **Run each backend call in the background and let it finish.** Never wrap one in
  a short foreground timeout. The wrapper is a parent process; killing it leaves an
  orphaned child holding that backend's cross-process rate-limit lock, and every
  later call to that backend then **hangs with no output and no error**. If a call
  must be abandoned, kill the process tree. Details in
  [references/backends.md](references/backends.md).
- **Cite every source.** Every backend skill requires that its use be disclosed and
  that the URLs/DOIs of all papers used be listed. The final report must carry a
  per-backend attribution line.
- **Report the coverage you actually queried** — which backends ran, which date
  windows, which filters. Never let a 1-backend run read as a comprehensive survey.
- **Sparse result sets are a finding, not a failure.** A zero-hit query and a
  malformed query look identical — show the query and confirm before concluding
  the literature is absent.

## Workflow

### Stage 0 — Classify the request

Decide which of these the user actually wants. They change which backends run:

| Intent | Backends | Notes |
|---|---|---|
| **Topic discovery / survey** | Europe PMC + PubMed | The default. Two independent sweeps, then merge. |
| **Known item** (title/DOI/citation) | Europe PMC (`DOI:`) → PubMed `match_raw_citations` → bioRxiv (DOI) | Don't sweep; resolve directly. |
| **What's new** (last 1–4 weeks) | bioRxiv by category (+ Europe PMC `FIRST_PDATE:` for what got published) | bioRxiv is the only fresh-preprint path. |
| **Read the full text** | Europe PMC → PubMed PMC | Only OA papers are retrievable; see Stage 3. |
| **Entity-centric** ("what genes does this paper implicate") | PubMed `find_linked_biological_data` | Unique to PubMed. |

Also fix, before running anything: the topic terms, any date window, language,
and whether the user wants preprints, published papers, or both. State the plan
back in one line before executing.

### Stage 1 — Run the sweeps

Two reference files, both worth reading before you run anything:

- **[references/backends.md](references/backends.md)** — exact invocations per backend.
  The argument lists are not guessable from function names.
- **[references/biology-query-cookbook.md](references/biology-query-cookbook.md)** —
  how to build the *query*: species and taxonomy terms, bioRxiv category names,
  verified `linkname` values, and how to handle a zero-result query.

- **Europe PMC** — the broad sweep, life-science-native and the richest syntax.
  **Append the all-access suffix** (see the OA policy section) so you get the whole
  corpus, not half of it.
- **PubMed** — MEDLINE, the curated complement. Prefer field tags (`[tiab]`,
  `[mesh]`, `[Organism]`) and proximity search (`"word1 word2"[tiab:~2]`) over bare
  boolean ANDs. Its relevance ranking for a well-formed MeSH query is usually better
  than a bare full-text search, which is why it earns a second sweep despite the
  smaller corpus.
- **bioRxiv** — only when the user wants recent preprints. **Size the window to the
  category, and expect it to be slow.** Measured on `ecology`: a **1-week** window
  was 1,490 records across **50 API pages** at 1 req/s, narrowing to 59 after the
  category filter and 6 after keywords. A 3-week window was still fetching past
  110 s. Use 1 week for a busy category, and reach for 4 weeks only in a sparse one.

Keep each sweep to ≤25 records. Do not page through large result sets without
confirming with the user — that is a 🔴 checkpoint in every backend skill.

Run both sweeps even when the first looks sufficient: they disagree in both
directions, and a one-backend answer cannot be distinguished from a complete one
by the reader.

### Stage 2 — Merge and de-duplicate

Different backends return different schemas. Normalise and collapse them:

```bash
uv run scripts/merge_results.py --out tmp_litsearch/merged.json \
  --input pubmed:tmp_litsearch/pubmed_abstracts.json \
  --input europepmc:tmp_litsearch/europepmc.json \
  --input biorxiv:tmp_litsearch/biorxiv.json
```

It matches on **any** of DOI, PMID or normalised title (in that priority), so a
record that carries only a PMID still collapses into the same paper's DOI-bearing
record from another backend — a single-key matcher silently returns duplicates.
It records which backends found each paper (multi-backend hits are a weak quality
signal) and reports per-backend overlap in `stats`. Read `stats` before the records.
Note the `unknown` access bucket is mostly PubMed rows: MEDLINE records carry no
OA flag.

`--input` is repeatable, so a backend can be passed more than once — but pass the
enriched file, not the same backend's raw PMID list alongside it.

### Stage 3 — Full text

Only open-access papers are retrievable. Try, in order:

1. **Europe PMC** `get_fulltext <PMCID>` (plain text) or `download_pdf <PMCID>`.
   Get the PMCID first with a `DOI:` search.
2. **PubMed** `get_full_text_pmc <PMID>` — PMC Open Access Subset only. Exits 1 and
   writes no file when the paper is not in that subset, so check the exit status.

Verify every downloaded file: PDFs must start with `%PDF-` and be non-trivial in
size. Exit code 0 does not prove you got a paper.

**A paper with no OA copy is a normal outcome**, not an error — report it as
"requires subscription / interlibrary loan" and move on. Never present an abstract
as if it were the full text.

### Stage 4 — Expand (only if the user asked to be thorough)

- **Citation graph** (Europe PMC only): `get_citations` / `get_references`.
- **Cross-database entities** (PubMed only): `find_linked_biological_data` →
  `fetch_database_summary`. Note: these links lag publication by weeks to months,
  so expect `[]` for recent papers.

### Stage 5 — Report

Structure the output as:

1. Attribution: which backends ran, with each backend's required source listing.
2. Coverage actually achieved: backends used, date windows, filters, and anything
   **not** searched.
3. The merged list. For each paper: title, year, journal, DOI link, **and its access
   status** (`OA` / `subscription` / `preprint`).
4. Explicitly flag: preprints (not peer-reviewed), retracted works, and any paper
   that only one backend returned.

## Europe PMC OA policy — a deliberate deviation

The stock Europe PMC skill document says:

> **Open Access Only**: This skill exclusively searches open-access content. The
> script automatically appends `OPEN_ACCESS:y` to every search query. Do NOT remove
> or override this filter.

`europepmc_api.py:141-142` implements that as:

```python
if "OPEN_ACCESS:" not in query.upper():
    query = f"({query}) AND OPEN_ACCESS:y"
```

**This orchestrator overrides that filter for discovery**, because it discards
42–61% of the biology literature, which defeats the purpose of this skill.

The override is done **in the query string**, never by editing the backend script —
so the backend skill is untouched and behaves exactly as before when used on its own:

| Mode | Append this to the query | Effect |
|---|---|---|
| **All access (default here)** | `AND (OPEN_ACCESS:y OR OPEN_ACCESS:n)` | Full corpus. Verified equal to the unfiltered baseline: `(zoology)` → 219,467; with suffix → 219,467. |
| **OA only** | *(nothing)* | Backend default. Use when the user only wants papers they can actually read. |

The suffix works because it contains the literal `OPEN_ACCESS:`, which trips the
guard on line 141 and suppresses the auto-append. `OPEN_ACCESS:*` also works.

**Always annotate results**: every Europe PMC record carries `isOpenAccess` — surface
it. PubMed's `"pmc open access"[filter]` and bioRxiv's preprint status do the same
job for the other two.

## Costs

All three backends are **free**.

- **PubMed**: free; `NCBI_API_KEY` raises the rate limit from 3 to 10 req/s.
- **Europe PMC**: free, 1 req/s.
- **bioRxiv**: free, but *very* sensitive to wide date ranges — see its anti-pattern.

## Backend-specific traps

- **bioRxiv is not a search engine.** Its API has no server-side keyword search; the
  script downloads a whole date range and filters locally. Windows must carry
  `--category`, and for a busy category should be 1 week, not the 4-week ceiling.
  For topical discovery, get DOIs elsewhere and use bioRxiv only by DOI. It also
  cannot download PDFs — use Europe PMC.
- **PubMed**: read the reference file for a function group before calling it —
  argument order is documented only there. Use `jq` to slim JSON before reading it
  into context.
- **Europe PMC**: 🔴 confirm before bulk PDF/full-text retrieval, before narrowing
  with a date window, and before treating a zero-result query as a real gap.

## Environment traps (measured on this machine)

These are not quirks of the backends' documentation — they were reproduced while
building this skill, and they cost real time to diagnose.

- **Orphaned backend processes block everything downstream.** Each backend CLI runs
  under `uv run` and rate-limits through `polite_http`, which is **cross-process**,
  keyed on a lock file per host. Killing only the wrapper — a timeout, a stopped
  background job, a closed terminal — leaves the child `python.exe` alive still
  holding that host's slot. Every later call to that backend then queues behind it
  and **hangs silently**. Measured: a Europe PMC search hung past 100 s; after
  killing the orphans the identical command finished in **3.5 s**. Note also that a
  `run.sh`-style wrapper script can itself survive a stopped job and keep respawning
  children, so check for the parent too.

  ```bash
  powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {
    \$_.Name -match '^(uv|python)\.exe\$' -and
    \$_.CommandLine -match 'europepmc_api|pubmed_api|search_by_dates'
  } | Select-Object ProcessId,Name"
  ```

  Kill those exact PIDs, then retry.
- **bioRxiv prints to stdout.** Only Europe PMC and PubMed take an output-path
  argument; bioRxiv needs a redirect. Piping to `jq` is fine, reading a raw dump
  into context is not.
- **Pass Windows-style paths to the merge script** (`D:/...`, not `/d/...`) — it is
  Python, and MSYS paths do not resolve.

## Directory layout

```
~/.claude/skills/biology-literature-search/
├── SKILL.md
├── README.md                       # human-facing overview, not read during a search
├── references/
│   ├── backends.md                 # verified invocation recipes per backend
│   ├── biology-query-cookbook.md   # how to build the query (species, categories, linknames)
│   └── coverage.md                 # measured coverage, what each backend misses
└── scripts/
    └── merge_results.py            # cross-backend de-duplication
```

`SKILL.md` is the operative document — an agent reads that. `README.md` is for
humans browsing the repository. On this machine the directory is a junction into
`~/.agents/skills/`, but nothing in the skill depends on that arrangement.
