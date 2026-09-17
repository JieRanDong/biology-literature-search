# biology-literature-search

A [Claude Code](https://claude.com/claude-code) skill that searches the biological
sciences literature across **three backends in one pass** — PubMed/MEDLINE,
Europe PMC, and bioRxiv/medRxiv — fetches the open-access full text of the papers it
recommends, and hands back a finished, formatted reading list.

The scope is **biology as a whole**, not just biomedicine: ecology, evolution,
zoology, plant science, microbiology, marine biology, genomics, taxonomy and the
molecular sciences all fall inside it.

You ask in prose. You get back a clean folder on disk — the papers themselves, one Excel
workbook, and nothing else. Every scratch file that produced them is filed away in
`_work/`, and any paper that could not be retrieved is recorded honestly in the workbook's
own columns rather than in a companion notes file.

This skill answers *which papers exist*, not *which order to read them in* — it ranks by
relevance and citation count, and will say so rather than invent a curriculum.

---

## Table of contents

- [Why it exists](#why-it-exists)
- [What you get](#what-you-get)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [The workflow](#the-workflow)
- [Full-text retrieval](#full-text-retrieval)
- [Design notes](#design-notes)
- [Repository layout](#repository-layout)
- [Known limitations](#known-limitations)
- [What was validated](#what-was-validated)
- [Attribution](#attribution)
- [Licence](#licence)

---

## Why it exists

No single database covers biology, and the gaps are wide enough to distort a
literature review.

**1. Europe PMC quietly discards half of its own corpus.** Its stock skill
force-appends `OPEN_ACCESS:y` to every query. Measured on 2026-09-17:

| Topic | skill default | full corpus | retained |
|---|---|---|---|
| zoology | 93,136 | 219,467 | 42% |
| ecology | 291,091 | 673,934 | 43% |
| evolutionary biology | 280,923 | 459,444 | 61% |
| plant biology | 314,140 | 606,089 | 52% |
| cell biology | 1,328,926 | 2,769,901 | 48% |

**2. Each backend is blind to something the others hold:**

| Backend | Blind to | Covered by |
|---|---|---|
| Europe PMC | non-OA full text (its *scope* is fine) | PubMed abstracts |
| PubMed | preprints; books; systematic-biology journals never indexed by MEDLINE; 4–8 week citation-link lag | bioRxiv, Europe PMC |
| bioRxiv | anything published before its date window; server-side keyword search does not exist | the other two, by DOI |

**3. And the standard way to fetch a paper is broken.** Three of the four obvious
PDF paths were measured failing (see [Full-text retrieval](#full-text-retrieval)),
so a skill that simply calls `download_pdf` and trusts the exit code will hand back
20 KB of HTML and call it a paper.

A single-database answer cannot be distinguished from a complete one by the reader.
That is the problem this skill exists to solve.

---

## What you get

The run is not finished until the deliverable exists on disk. Terminal prose is a
summary, never the deliverable.

**The finished folder is exactly this** — nothing else:

```
<dir>/
├── 文献清单.xlsx          # the deliverable
├── _paper/                # the downloaded papers
└── _work/                 # everything that produced them
```

| Item | What it is |
|---|---|
| `文献清单.xlsx` | The deliverable. **Sheet 1 `推荐文献`** — 序号 / 文章名 / 期刊名 / 地址 / 年份 / 获取状态 / 本地文件 / 备注, with clickable DOI links colour-coded by retrieval status. **Sheet 2 `全部检索结果`** — every de-duplicated record from all three backends, filterable. |
| `_paper/NN_<slug>.pdf` / `.txt` / `.fulltext.xml` | The downloaded papers. `NN` is the reading-order number, so the folder itself encodes the reading order. |
| `_work/` | `selection.json`, `merged.json` and the raw per-backend JSON. Nothing is deleted — `build_report.py` can be re-run from here. |

A paper behind a paywall is reported as **需订阅 / 馆际互借** in the 获取状态 column. It is
never silently dropped, never passed off as read, and never swapped for a different paper.

> **Two documents earlier versions of this skill produced are deliberately gone**: a
> `未下载文献说明.txt` and a `学习顺序说明.md`. Retrieval status lives in the workbook's
> 获取状态 / 本地文件 / 备注 columns instead, and the skill answers *which papers exist*
> rather than *which order to read them in*.

---

## How it works

This skill is an **orchestrator**. It picks the backends that can answer the
question, runs them, merges what comes back, then goes and gets the PDFs.

```
  user question
        │
        ▼
  ┌────────────────┐   survey / known item / recency sweep /
  │   Stage 0      │   full text / entity-centric
  │   classify     │   + collect the delivery dir and a Unpaywall email
  └───────┬────────┘
          │
    ┌─────┴──────────────────┬──────────────────┐
    ▼                        ▼                  ▼
┌────────────┐        ┌────────────┐     ┌────────────┐
│ Europe PMC │        │  PubMed    │     │  bioRxiv   │
│ broad      │        │ MEDLINE    │     │ preprints  │
│ + fulltext │        │ + cross-   │     │ by subject │
│ + citations│        │   links    │     │ category   │
└─────┬──────┘        └─────┬──────┘     └─────┬──────┘
      └─────────────────────┼──────────────────┘
                            ▼
                 ┌──────────────────────┐
                 │  Stage 2   merge     │  de-duplicate on DOI / PMID / title
                 │  merge_results.py    │  annotate access: OA / subscription / preprint
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │  Stage 3   full text │  six-step fallback chain,
                 │  fallback chain      │  every file verified by magic bytes
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │  Stage 5   build     │  文献清单.xlsx
                 │  build_report.py     │  _paper/  ← downloaded papers
                 │  finalize_delivery.py│  _work/   ← scratch
                 └──────────────────────┘
```

**It never copies or patches the backend skills.** All three are invoked in place by
absolute path, exactly as their own `SKILL.md` documents them. Upstream fixes — and
any local optimisations you make to those skills — propagate automatically. The only
thing changed about Europe PMC's behaviour is the *query string* (see
[Design notes](#design-notes)).

---

## Requirements

| Requirement | Notes |
|---|---|
| [Claude Code](https://claude.com/claude-code) | the host application |
| [`uv`](https://docs.astral.sh/uv/) on `PATH` | all three bundled scripts are PEP-723; `build_report.py` pulls in `openpyxl` automatically, nothing to install by hand |
| Three backend skills | **not bundled in this repository** — see [Installation](#installation) |
| **A contact email** | for Unpaywall (Stage 3 step 2). The skill will ask you for one; it will not invent a plausible-looking address, because Unpaywall accepts a well-formed fake silently and fails invisibly |
| `NCBI_API_KEY` *(optional)* | raises PubMed's rate limit from 3 to 10 req/s; put it in `~/.env` |

Searching is **free** on all three backends. There are no paid APIs and no required
keys.

---

## Installation

### 1. This skill

```bash
git clone https://github.com/JieRanDong/biology-literature-search.git \
  ~/.claude/skills/biology-literature-search
```

Claude Code discovers skills in `~/.claude/skills/`, so that is all that is needed.

### 2. Its three backends

They come from
[`google-deepmind/science-skills`](https://github.com/google-deepmind/science-skills)
and are **not** redistributed here. Note that the upstream directories use
underscores while the installed names use hyphens — the paths inside
`references/backends.md` expect the hyphenated names:

```bash
git clone --depth 1 https://github.com/google-deepmind/science-skills.git /tmp/science-skills

cp -r /tmp/science-skills/skills/literature_search_europepmc ~/.claude/skills/literature-search-europepmc
cp -r /tmp/science-skills/skills/literature_search_biorxiv   ~/.claude/skills/literature-search-biorxiv
cp -r /tmp/science-skills/skills/pubmed_database             ~/.claude/skills/pubmed-database
```

If you use a skill manager instead, install them under those hyphenated names.

---

## Usage

The skill triggers from natural language — you do not invoke it by name. Example
prompts:

```
Find everything published on coral bleaching thermal tolerance.
生态学里关于草原干旱恢复力的文献有哪些？
帮我找 5 篇关于植物免疫信号传导的综述，下载全文。
What's come out in the last two weeks on plant immune signalling?
Which genes does this paper implicate?  (PMID 38351328)
Has anyone cited the 2021 AlphaFold paper in an ecology context?
```

A typical run hands back a folder like:

```
tmp_litsearch/
├── 文献清单.xlsx
├── _paper/
│   ├── 01_publisher-oa-link.pdf
│   ├── 02_unpaywall.pdf
│   └── 03_pmc-fulltext.fulltext.xml
└── _work/
    ├── selection.json
    ├── merged.json
    └── …                  # raw per-backend JSON
```

The trigger is deliberately broad: broad biology surveys, "find papers on \<organism
or topic\>", systematic searches, and citation chasing.

---

## The workflow

| Stage | What happens |
|---|---|
| **0 — Classify** | Decide whether the user wants a survey, a known item, a recency sweep, full text, or entity lookups — and fix the delivery directory plus a Unpaywall contact email. This determines which backends run. |
| **1 — Sweep** | Query the chosen backends. Both Europe PMC and PubMed run for a topical survey; bioRxiv only for recency. Each backend gets its query written in *its own* idiom — they are not interchangeable. |
| **2 — Merge** | `scripts/merge_results.py` normalises the three different result schemas, collapses duplicates, and annotates access status. |
| **3 — Full text** | A six-step fallback chain: publisher OA link → Unpaywall → PubMed `get_full_text_pmc` → Europe PMC `get_fulltext` → EBI REST JATS XML → give up and record why. Every file is verified by magic bytes, not by exit code. |
| **4 — Expand** *(optional)* | Europe PMC citation graph; PubMed cross-links to Gene / Protein / Nucleotide / PubChem / SRA records. |
| **5 — Deliverables** | Assemble `selection.json`, download every item into `_paper/`, build `文献清单.xlsx` via `scripts/build_report.py`, then run `scripts/finalize_delivery.py` — which files the papers into `_paper/`, sweeps the scratch into `_work/`, and verifies every promised file is really on disk. |

The skill carries hard checkpoints: it must confirm before bulk retrieval, before
reporting zero results as a finding, and before quoting a citation count as a fact.

**How the curated list is sized**, in priority order — and it states which it used:

1. You named a count ("find me 5 papers") → that count.
2. You named a type ("3 reviews") → filter to that type, then rank.
3. Neither → 5 papers, ranked by the sort chosen at Stage 1, capped at 25.

The list is never padded to reach a count, and a paper you asked for by name is never
silently dropped.

---

## Full-text retrieval

**The obvious path is broken — do not start there.** All four rows were measured on
2026-09-17:

| Attempt | Result |
|---|---|
| `europepmc.org/articles/<PMCID>?pdf=render` — what the upstream `download_pdf` calls | **HTTP 403**, and the body is the Cloudflare `Just a moment...` JS challenge |
| `oa.fcgi?id=<PMCID>` — NCBI OA Web Service | **HTTP 404**, service retired |
| `pmc.ncbi.nlm.nih.gov/articles/<PMCID>/pdf/` | **HTTP 301** to a filename-specific URL, which then returns **HTTP 200 with ~1.8 KB of HTML** — a `Preparing to download ...` interstitial, not a PDF. Also slow enough to time out at 25 s |
| publisher OA direct link (BMC/Springer, Nature family) | ✅ works |

The 403 page blames an empty User-Agent and tells you to set `POLITE_HTTP_USER_AGENT`.
**That hint is wrong** — these results were reproduced with a real browser User-Agent,
so the UA is not the cause.

So the skill works down a chain and stops at the first file that passes *its own*
test:

| # | Step | Verification |
|---|---|---|
| 1 | Publisher OA direct link (`…/counter/pdf/<doi>.pdf`, `nature.com/articles/<id>.pdf`) | starts with `%PDF-` |
| 2 | [Unpaywall](https://unpaywall.org/) `best_oa_location.url_for_pdf`, then every `oa_locations[]` entry | starts with `%PDF-` |
| 3 | PubMed PMC Open Access Subset — `get_full_text_pmc`, BioC JSON, **not** a PDF | parses as BioC JSON |
| 4 | Europe PMC `get_fulltext <PMCID>` — plain text | non-empty, not an HTML error page |
| 5 | Europe PMC `get_fulltext <PMCID> --format xml` — JATS XML, complete readable full text but not a typeset PDF | non-empty, starts `<?xml` |
| 6 | Give up on this paper | record `status: 未下载` and the reason in that item's `note` |

Three details that matter more than they look:

- **Verification is per-step and by content, not by exit code.** A 20 KB HTML
  interstitial writes to disk just as happily as a real PDF. A file that fails its
  test is deleted, not kept.
- **Step 3's exit code is ambiguous.** It exits 1 both when the paper is outside the
  OA subset *and* for unrelated causes — a stale output path, a missing argument. Only
  a response body reading `[Error] : No result can be found.` is paywall evidence;
  anything else means fix-and-retry, not 需订阅.
- **Steps 1–2 are the only raw-HTTP calls in the skill.** No wrapper reaches
  publisher hosts or Unpaywall, so they are an explicit exception to the "always use
  the wrapper" rule — bounded to one request per URL, a self-identifying User-Agent,
  and no retry loop.

---

## Design notes

### Europe PMC: the OA filter is bypassed in the query string, not in code

The upstream `europepmc_api.py:141-142` does:

```python
if "OPEN_ACCESS:" not in query.upper():
    query = f"({query}) AND OPEN_ACCESS:y"
```

Appending `AND (OPEN_ACCESS:y OR OPEN_ACCESS:n)` contains the literal token
`OPEN_ACCESS:`, so the guard trips and nothing is appended — and the clause itself
matches everything. Verified equal to the unfiltered baseline exactly:
`(zoology)` → 219,467; with the suffix → 219,467.

The upstream skill is untouched and behaves exactly as before when used on its own.
**This deliberately overrides an upstream instruction** ("Do NOT remove or override
this filter") because that filter defeats the purpose of a broad biology search. The
OA-only mode is still available by simply omitting the suffix.

### Merging matches on any identity, not one

`merge_results.py` registers *all* of a record's identities — DOI, `pmid:`, and
normalised title — and matches a later record against any of them. A single-key
matcher silently returns duplicates whenever one backend supplies a DOI and another
carries only a PMID for the same paper.

### Escaped markup is decoded before tags are stripped

Europe PMC escapes its inline JATS markup, so a title arrives as
`… Detection of &lt;i&gt;Cladocopium thermophilum&lt;/i&gt; …`. Stripping `<…>` tags
before decoding entities leaves a literal `i` / `/i` in the output. `clean_text()`
decodes first, then strips.

### A backend that contributes nothing says so

If an input file yields zero records — empty, or simply not that backend's output
shape — the merge prints a warning to stderr rather than quietly omitting it.

### The report builder refuses to guess

`build_report.py` asserts that the record statuses partition the list across exactly
three buckets (`已下载 PDF` / `已下载全文（非 PDF）` / `未下载`) and exits on a typo'd
status, so a paper cannot silently vanish from the counts. `finalize_delivery.py` adds
the complementary guarantee: it **exits 1** if any `local_file` in `selection.json`
does not resolve to a real file, so a `已下载` claim always has a paper behind it.
Together these mean the workbook cannot overstate what was retrieved — which matters
more now that there is no companion notes file to cross-check it against.

---

## Repository layout

```
SKILL.md                           481 lines   the operative document; an agent reads this
README.md                                      this file — for humans, not read during a search
references/
  backends.md                      248 lines   exact CLI invocation per backend, plus troubleshooting
  biology-query-cookbook.md        120 lines   species queries, linkname table, bioRxiv categories
  coverage.md                       86 lines   measured coverage and what each backend misses
scripts/
  merge_results.py                 357 lines   cross-backend de-duplication and access annotation (stdlib only)
  build_report.py                  188 lines   文献清单.xlsx builder (PEP-723: openpyxl)
  finalize_delivery.py             141 lines   file papers into _paper/, scratch into _work/, verify promises (stdlib only)
```

---

## Known limitations

- **OpenAlex is not wired in.** Its CLI returns HTTP 429 on even a single plain call
  in some environments, then sleeps ≥180 s per retry across 6 attempts, which reads
  as a multi-minute hang. This was reproducible here while `curl` against the
  *identical URL* returned 200 at the same moment — and was **not** explained by
  User-Agent, `Accept-Encoding`, IP family, or HTTP version. The mechanism is
  unidentified. Set `OPENALEX_API_KEY` and add the backend manually if you want it;
  the CLI never sends a `mailto`, so the polite pool is not an option.
- **`download_pdf` on Europe PMC does not work** (403, Cloudflare). The skill routes
  around it; the upstream skill does not. See
  [Full-text retrieval](#full-text-retrieval).
- **Raw HTTP is used in exactly two places** — publisher OA hosts and Unpaywall.
  Those steps depend on third-party endpoints that can change without notice; the
  measured results above are a snapshot, not a guarantee.
- **bioRxiv sweeps are slow by design.** Its API has no server-side keyword search,
  so the script downloads an entire date window and filters locally. Measured on
  `ecology`: a **1-week** window is 1,490 records across **50 API pages**, narrowing
  to 59 after the category filter and 6 after keywords. It is for deliberate recency
  sweeps, not topical discovery.
- **`arxiv` is excluded.** Its biology coverage is only the `q-bio` sliver.
- **Full text means open-access full text.** A paywalled paper is reported as
  需订阅 / 馆际互借 — never passed off as read.
- **`selection.json` uses Chinese status strings** (`已下载 PDF` etc.) and the
  workbook sheets are named in Chinese. The skill's prose is English; the deliverables
  are Chinese.
- **Backend CLIs can orphan themselves.** They run under `uv run` and rate-limit
  through `polite_http`, which is cross-process. Killing only the wrapper leaves a
  child holding that host's lock, and every later call to that backend hangs with no
  output. Run them in the background and let them finish. See
  `references/backends.md` → *Troubleshooting*.

---

## What was validated

Everything claimed above was run, not assumed:

- Europe PMC, PubMed and bioRxiv backends exercised end-to-end against live APIs;
  `hitCount` values recorded.
- The OA bypass confirmed equal to the unfiltered baseline (`(zoology)` → 219,467
  both ways) and confirmed to surface records the default filter hides (a real
  `isOpenAccess: N` row appeared in results).
- The merge script run against real captured backend output: 3 backends → 10 unique
  records, correct `access` classification (`OA 4 / subscription 1 / preprint 1 /
  unknown 4`), PMID-only records collapsing into their DOI-bearing counterparts and
  inheriting their titles.
- The failing download paths reproduced independently with a real browser
  User-Agent: `?pdf=render` → HTTP 403 with a Cloudflare challenge body; `oa.fcgi`
  → HTTP 404; PMC `/pdf/` → HTTP 301, then 200 with an HTML `Preparing to
  download ...` interstitial. That is the basis for the fallback chain, rather than
  a hopeful `download_pdf` call.
- Query syntaxes in the cookbook measured against live APIs — including the finding
  that PubMed's undocumented `[Organism]` tag works (67,990 hits for *Danio rerio*)
  while Europe PMC's `ORGANISM:` field does not (151 hits).
- The delivery pipeline run end-to-end on fixtures: `build_report.py` produced a
  workbook with both sheets and the expected bucket counts, and `finalize_delivery.py`
  sorted a flat directory into exactly `文献清单.xlsx` + `_paper/` + `_work/` with
  nothing left loose and nothing deleted. The integrity check was exercised in both
  directions — exit 0 when every `local_file` resolves, **exit 1** listing the offender
  when one does not.

This skill has also been through several rounds of automated adversarial
optimisation (`darwin-skill`) — seven optimisation passes in total, each judged blind
against the previous version.

---

## Attribution

This repository contains **only the orchestration layer**. The retrieval itself is
done by three separate skills from
[`google-deepmind/science-skills`](https://github.com/google-deepmind/science-skills):

- `literature_search_europepmc`
- `literature_search_biorxiv`
- `pubmed_database`

They are not redistributed here and carry their own terms — check them, along with
the licence of any paper you retrieve. Unpaywall data is free under
[their terms](https://unpaywall.org/products/api).

---

## Licence

No licence file is included. Absent one, the default is all rights reserved — add
one if you intend others to reuse this.
