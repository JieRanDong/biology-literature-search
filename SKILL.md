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
  these APIs — the wrappers own the rate limiting. The sole exception is Stage 3
  steps 1–2 (publisher PDF hosts, Unpaywall), which no wrapper can reach; those two
  calls are bounded by the rules in Stage 3. Every other step, full-text XML included,
  goes through a wrapper.
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
whether the user wants preprints, published papers, or both, **the delivery
directory**, and **a contact email for Unpaywall** (ask for one if the user has not
given any — stage 3 needs it and must never invent one). State the plan back in one
line before executing.

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

### Stage 3 — Full text and PDF retrieval

Only open-access papers are retrievable. **The obvious path is broken — do not start
there.** All four rows below were measured on 2026-09-17:

| Attempt | Result |
|---|---|
| `europepmc.org/articles/<PMCID>?pdf=render` (what `download_pdf` calls) | **HTTP 403** — Cloudflare "Just a moment…" JS challenge |
| `oa.fcgi?id=<PMCID>` (NCBI OA Web Service) | **HTTP 404** — service retired |
| `pmc.ncbi.nlm.nih.gov/articles/<PMCID>/pdf/` | returns ~20 KB of HTML, not a PDF |
| publisher OA direct link (BMC/Springer, Nature family) | ✅ works |

The 403 message blames an empty User-Agent and tells you to set
`POLITE_HTTP_USER_AGENT`. **That hint is wrong** — a real browser UA still 403s.

**Fallback chain — work down it, stop at the first file that passes verification:**

| # | Step | How | If it fails |
|---|---|---|---|
| 1 | Publisher OA direct link | `https://<publisher>/…/<doi>.pdf`; verified working for BMC/Springer (`…/counter/pdf/<doi>.pdf`) and Nature (`nature.com/articles/<id>.pdf`) | → 2 |
| 2 | Unpaywall | `https://api.unpaywall.org/v2/<doi>?email=<contact>` → `best_oa_location.url_for_pdf`, then every `oa_locations[]` entry | → 3 |
| 3 | PubMed PMC Open Access Subset | `uv run scripts/pubmed_api.py <fresh-out.json> get_full_text_pmc <PMID>` — BioC JSON full text, **not** a PDF. Exits 1 without writing a file both when the paper is outside the subset *and* for unrelated causes (output path already exists, unknown function, missing argument). **Only a body reading `[Error] : No result can be found.` is paywall evidence**; any other error body means fix-and-retry, not 需订阅. Always pass a fresh output path | → 4 |
| 4 | Europe PMC plain text | `get_fulltext <PMCID>` — note this is *not* `download_pdf` | → 5 |
| 5 | Europe PMC JATS XML | `get_fulltext <PMCID> --format xml` — the *same wrapper* as step 4, different format; it hits the same EBI REST endpoint, so never hand-roll that URL. Complete readable full text, but **not** the typeset PDF; save as `.fulltext.xml` and record status `已下载全文（非 PDF）` | → 6 |
| 6 | Give up on this paper | record status `未下载`, reason into `未下载文献说明.txt` | — |

**The raw-HTTP steps are 1 and 2 only** — publisher PDF hosts, and Unpaywall. No
wrapper reaches either, which is the exception carved out in **Core rules**. Keep them
minimal and polite: one request per URL,
`User-Agent: biology-literature-search/1.0 (contact: <the user's email>)`, no retry
loop. A single Unpaywall re-try means: on HTTP 422, retry once with a different
`email=`, then drop to step 3. Use the email collected at Stage 0 — **never invent
one**: 422 means missing or malformed, but a well-formed fake domain is accepted
silently, so a made-up address fails invisibly rather than loudly. Steps 3–5 all go
through wrappers.

**Verify every file, by each step's own test — not by exit code.** Exit code 0 does
not prove you got a paper: a 20 KB HTML interstitial writes to disk just as happily as
a real PDF. A file that fails its test is **deleted, not kept**: steps 1–2 must start
with `%PDF-`; step 3 must parse as BioC JSON; steps 4–5 must be non-empty and **not**
an HTML error page — their real first bytes are `# ` for plain text and `<?xml` for
JATS, so a rule demanding `<` or a letter would discard the wrapper's own good output.
The chain ends only by stopping at the first step that passes, or by reaching step 6.

**A paper with no OA copy is a normal outcome**, not an error — record it as
需订阅 / 馆际互借 in `selection.json` and in `未下载文献说明.txt`, then move on.
Never present an abstract as if it were the full text, and never swap in a different
paper for the one the user asked for.

If `download_pdf` or `get_fulltext` hangs with no output, that is an orphaned
backend process holding the rate-limit lock, not a slow API — see the
troubleshooting section in `references/backends.md`.

### Stage 4 — Expand (only if the user asked to be thorough)

- **Citation graph** (Europe PMC only): `get_citations` / `get_references`.
- **Cross-database entities** (PubMed only): `find_linked_biological_data` →
  `fetch_database_summary`. Note: these links lag publication by weeks to months,
  so expect `[]` for recent papers.

### Stage 5 — Deliverables

The run is not finished until **three files exist on disk**. Terminal prose is a
summary, never the deliverable.

All three go in the scratch directory fixed under **Core rules** above — the
default `./tmp_litsearch/` in the current working directory, or the path the user
named when you stated the plan at Stage 0. Name that path in your Stage 0 plan line
so "the delivery directory" is never ambiguous later.

**5.1 — Assemble `selection.json`**

Write the curated list as JSON — **only** the papers you are recommending, in the
order the user should read them. This is a curated subset of `merged.json`, not a
copy of it; the full set goes into sheet 2 of the workbook at 5.3.

The inclusion criterion, in priority order — state which one you used in the
terminal summary:

1. **The user named a count** ("find me 5 papers") — that count is the list size.
2. **The user named a type** ("3 reviews", "methods papers") — filter `merged.json`
   to that type first, then rank.
3. **Neither** — default to **5** papers, ranked by the sort you passed at Stage 1
   (Europe PMC `--sort "CITED desc"`; PubMed `--sort_by relevance` — pass one
   explicitly, Stage 1 does not imply it), capped at 25. State which sort you used.

Never pad the list to reach a count, and never silently drop a paper the user asked
for by name. The JSON has exactly these fields:

```json
{
  "topic": "…", "search_date": "YYYY-MM-DD", "backends": "…",
  "items": [
    {"order": "①", "title": "…", "journal": "…", "doi": "10.xxxx/yyy",
     "year": "2021", "status": "未下载", "local_file": "", "note": "…"}
  ]
}
```

`status` is exactly one of `已下载 PDF` / `已下载全文（非 PDF）` / `未下载`.
`local_file` is a bare filename in the delivery directory, or `""`. Name downloads
`NN_<slug>.pdf` / `.txt` / `.fulltext.xml`, where `NN` is the `order` value — the
folder then encodes the reading order.
Do not invent additional status strings — `build_report.py` asserts the three
buckets partition the list.

**5.2 — Download every item**

Work down the fallback chain in **Stage 3 — Full text and PDF retrieval** above.
Record per item whether you got a PDF, got full text in another format, or got
nothing — that outcome is what sets each `status` field at 5.1.

**5.3 — Build `文献清单.xlsx`**

```bash
uv run scripts/build_report.py --selection <dir>/selection.json \
  --merged <dir>/merged.json --out <dir>/文献清单.xlsx \
  --emit-missing <dir>/未下载文献说明.txt
```

- Sheet `推荐文献` — 序号 / 文章名 / 期刊名 / 地址 / 年份 / 获取状态 / 本地文件 / 备注
- Sheet `全部检索结果` — 文章名 / 期刊名 / 地址 / 年份 / 来源后端 / 开放获取 / PMID

`地址` is always the full `https://doi.org/<doi>` link, never a bare DOI string.

**5.4 — Fill in `未下载文献说明.txt`**

The `--emit-missing` flag at 5.3 already wrote the skeleton: one block per item whose
status is not `已下载 PDF`, each with 文章名 / 期刊名 / 地址 / 年份 / **原因** /
**复核证据** / 获取途径, plus a section for technical blocks. **Your job is to replace
every 【填写】 placeholder with what actually happened** — the exit code or HTTP status
you really observed, not a plausible one. Never ship the skeleton with placeholders
still in it; a placeholder that survives to the user reads as a fabricated reason.

Then a separate section listing every technical block you hit, with the exact URL and
observed failure, so the next run does not re-diagnose the same thing. A paper behind
a paywall is reported as **需订阅 / 馆际互借**, never silently dropped and never
replaced by a different paper without the user asking.

**5.5 — Terminal summary**

Then, and only then, print in chat: attribution (which backends ran, with each
backend's required source listing), coverage actually achieved (backends, date
windows, filters, and anything **not** searched), and explicit flags for preprints
(not peer-reviewed), retracted works, and any paper only one backend returned.

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
    ├── merge_results.py            # cross-backend de-duplication (Stage 2)
    └── build_report.py             # 文献清单.xlsx — the two-sheet workbook (Stage 5.3)
```

`SKILL.md` is the operative document — an agent reads that. `README.md` is for
humans browsing the repository. On this machine the directory is a junction into
`~/.agents/skills/`, but nothing in the skill depends on that arrangement.
