# biology-literature-search

A [Claude Code](https://claude.com/claude-code) skill that searches the biological
sciences literature across **three backends in one pass** — PubMed/MEDLINE,
Europe PMC, and bioRxiv/medRxiv — then merges and de-duplicates the results into a
single list annotated with each paper's access status.

The scope is **biology as a whole**, not just biomedicine: ecology, evolution,
zoology, plant science, microbiology, marine biology, genomics, taxonomy and the
molecular sciences all fall inside it.

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

A single-database answer cannot be distinguished from a complete one by the reader.
That is the problem this skill exists to solve.

---

## How it works

This skill is an **orchestrator**. It picks the backends that can answer the
question, runs them, and merges what comes back.

```
  user question
        │
        ▼
  ┌──────────────┐   classify the request: survey / known item /
  │   Stage 0    │   recency sweep / full text / entity-centric
  │   route      │
  └──────┬───────┘
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
              one ranked, access-annotated list
```

**It never copies or patches the backend skills.** All three are invoked in place
by absolute path, exactly as their own `SKILL.md` documents them. Upstream fixes —
and any local optimisations you make to those skills — propagate automatically.
The only thing that changed about Europe PMC's behaviour is the *query string*
(see [Design notes](#design-notes)).

---

## Requirements

| Requirement | Notes |
|---|---|
| [Claude Code](https://claude.com/claude-code) | the host application |
| [`uv`](https://docs.astral.sh/uv/) on `PATH` | every backend CLI is a PEP-723 script executed via `uv run` |
| Three backend skills | **not bundled in this repository** — see [Installation](#installation) |
| `NCBI_API_KEY` *(optional)* | raises PubMed's rate limit from 3 to 10 req/s; put it in `~/.env` |

Everything this skill uses is **free**. There are no paid APIs and no required
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
What's come out in the last two weeks on plant immune signalling?
Which genes does this paper implicate?  (PMID 38351328)
I need to actually read these papers, not just the abstracts.
Has anyone cited the 2021 AlphaFold paper in an ecology context?
```

The trigger is deliberately broad: broad biology surveys, "find papers on \<organism
or topic\>", systematic searches, and citation chasing.

---

## The workflow

| Stage | What happens |
|---|---|
| **0 — Classify** | Decide whether the user wants a survey, a known item, a recency sweep, full text, or entity lookups. This determines which backends run. |
| **1 — Sweep** | Query the chosen backends. Both Europe PMC and PubMed run for a topical survey; bioRxiv only for recency. Each backend gets its query written in *its own* idiom — they are not interchangeable. |
| **2 — Merge** | `scripts/merge_results.py` normalises the three different result schemas, collapses duplicates, and annotates access status. |
| **3 — Full text** | Europe PMC `get_fulltext` / `download_pdf`, falling back to PubMed's PMC subset. Every downloaded PDF is verified to be non-empty and start with `%PDF-`. |
| **4 — Expand** *(optional)* | Europe PMC citation graph; PubMed cross-links to Gene / Protein / Nucleotide / PubChem / SRA records. |
| **5 — Report** | Which backends ran, the exact queries, each backend's `hitCount`, any filters applied, and the access status of every paper listed. |

The skill carries hard checkpoints: it must confirm before bulk retrieval, before
reporting zero results as a finding, and before quoting a citation count as a fact.

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

---

## Repository layout

```
SKILL.md                           295 lines   the operative document; an agent reads this
README.md                                      this file — for humans, not read during a search
references/
  backends.md                      248 lines   exact CLI invocation per backend, plus troubleshooting
  biology-query-cookbook.md        120 lines   species queries, linkname table, bioRxiv categories
  coverage.md                       86 lines   measured coverage and what each backend misses
scripts/
  merge_results.py                 357 lines   cross-backend de-duplication and access annotation
```

---

## Known limitations

- **OpenAlex is not wired in.** Its CLI returns HTTP 429 on even a single plain
  call in some environments, then sleeps ≥180 s per retry across 6 attempts, which
  reads as a multi-minute hang. This was reproducible here while `curl` against the
  *identical URL* returned 200 at the same moment — and was **not** explained by
  User-Agent, `Accept-Encoding`, IP family, or HTTP version. The mechanism is
  unidentified. Set `OPENALEX_API_KEY` and add the backend manually if you want it;
  the CLI never sends a `mailto`, so the polite pool is not an option.
- **bioRxiv sweeps are slow by design.** Its API has no server-side keyword search,
  so the script downloads an entire date window and filters locally. Measured on
  `ecology`: a **1-week** window is 1,490 records across **50 API pages**, narrowing
  to 59 after the category filter and 6 after keywords. It is for deliberate recency
  sweeps, not topical discovery.
- **`arxiv` is excluded.** Its biology coverage is only the `q-bio` sliver.
- **Full text means open-access full text.** A paywalled paper is reported as
  "requires subscription / interlibrary loan" — never passed off as read.
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
- Query syntaxes in the cookbook measured against live APIs — including the finding
  that PubMed's undocumented `[Organism]` tag works (67,990 hits for *Danio rerio*)
  while Europe PMC's `ORGANISM:` field does not (151 hits).

---

## Attribution

This repository contains **only the orchestration layer**. The retrieval itself is
done by three separate skills from
[`google-deepmind/science-skills`](https://github.com/google-deepmind/science-skills):

- `literature_search_europepmc`
- `literature_search_biorxiv`
- `pubmed_database`

They are not redistributed here and carry their own terms — check them, along with
the licence of any paper you retrieve.

---

## Licence

No licence file is included. Absent one, the default is all rights reserved — add
one if you intend others to reuse this.
