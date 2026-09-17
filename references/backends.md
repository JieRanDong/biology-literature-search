# Backend invocation recipes

Verified argument lists for the three backends. **These are transcriptions of each
backend's own documentation — if a backend skill is updated, re-read its `SKILL.md`
and its `references/` before trusting this file.**

## Running any backend

Every backend script uses paths relative to its own skill directory, so `cd` there
first. Set `PYTHONUTF8=1` on Windows to avoid encoding failures on non-ASCII output.

**Output conventions differ — this is the easiest thing to get wrong:**

| Backend | How results are written |
|---|---|
| Europe PMC | `--output <file>` (required) |
| PubMed | **first positional arg** is the output file; refuses to overwrite |
| bioRxiv | redirect stdout: `> file.json` |

---

## PubMed — MEDLINE coverage and cross-database links

Skill: `~/.claude/skills/pubmed-database/`
Run from: `~/.claude/skills/pubmed-database`

```bash
cd ~/.claude/skills/pubmed-database

# Search — output is a bare JSON list of PMIDs
uv run scripts/pubmed_api.py ./tmp_litsearch/pubmed_pmids.json \
  search_pubmed "gut microbiome[tiab] AND (metagenomics[tiab] OR sequencing[tiab])" \
  --max_results 25 --sort_by relevance

# Chain: turn the PMID list into a comma-separated string
cat ./tmp_litsearch/pubmed_pmids.json | jq -r 'join(",")'

# Fetch metadata + abstracts
uv run scripts/pubmed_api.py ./tmp_litsearch/pubmed_abstracts.json \
  fetch_article_abstracts "35113657,31234568"

# Spell-check a term first if the user's terminology is uncertain
uv run scripts/pubmed_api.py ./tmp_litsearch/spelling.json \
  verify_medical_spelling "rhuematoid arthritus"

# Resolve a messy citation to a PMID (pipe-delimited, trailing pipe REQUIRED)
uv run scripts/pubmed_api.py ./tmp_litsearch/citation_pmids.json \
  match_raw_citations "nature|2006||||takahashi k|key0|"

# Full text (PMC Open Access Subset only)
uv run scripts/pubmed_api.py ./tmp_litsearch/ft_35113657.json get_full_text_pmc "35113657"

# Link a paper to gene records, then resolve the opaque UIDs
uv run scripts/pubmed_api.py ./tmp_litsearch/gene_links.json \
  find_linked_biological_data "35113657" gene pubmed_gene
uv run scripts/pubmed_api.py ./tmp_litsearch/gene_summary.json \
  fetch_database_summary gene "43740568"

# Don't know which linknames exist? Ask.
uv run scripts/pubmed_api.py ./tmp_litsearch/links.json discover_available_links "35113657"
```

Argument lists (positional-first output file, then function name, then positional args):

| Function | Required args | Output |
|---|---|---|
| `search_pubmed` | `query`; `--max_results` (10), `--sort_by` (`relevance`/`pub_date`/`Author`/`JournalName`/`Title`) | `["35113657", ...]` |
| `fetch_article_abstracts` | `pmids` (comma-sep); `--webenv`, `--query_key` | `[{pmid,title,authors,journal,pubdate,doi,abstract}]` |
| `verify_medical_spelling` | `term` | `{original, corrected}` |
| `match_raw_citations` | `citation_strings` (comma-sep pipe-delimited) | `["16904174"]` |
| `get_full_text_pmc` | `pmid` | `{pmid, full_text}` or `{error, endpoint}` |
| `find_linked_biological_data` | `source_pmid`, `target_database`, `linkname`; `--dbfrom` (`pubmed`), `--mindate`, `--maxdate`, `--webenv`, `--query_key` | `["123456", ...]` |
| `discover_available_links` | `source_id`; `--dbfrom` (`pubmed`) | `[{linkname, db}]` |
| `fetch_database_summary` | `database`, `id_list` (comma-sep) | list of DB-specific objects |
| `global_database_discovery` | `query` | `{dbname: count}` |

Query syntax that matters for biology:

- `[tiab]` title/abstract, `[mesh]` MeSH terms, `[pt]` publication type, `[dp]` date.
- Proximity: `"gut microbiome"[tiab:~2]` — better than `AND` for multi-word concepts.
- Relative dates: `"last 6 months"[dp]`.
- OA pre-filter, so you don't waste full-text calls: `AND "pmc open access"[filter]`.
- Genes and species: MEDLINE is the only backend here with curated gene links
  (`pubmed_gene`) — use it for "which genes does this literature implicate" questions.

Trap: `title` and `abstract` both `null` means a dead record, not a missing fetch.
The CLI refuses to overwrite an existing output file — on retry, use a **new** path.

---

## Europe PMC — full text, PDF and the citation graph

Skill: `~/.claude/skills/literature-search-europepmc/`
Run from: `~/.claude/skills/literature-search-europepmc`

```bash
cd ~/.claude/skills/literature-search-europepmc

# All-access sweep — the suffix is REQUIRED (see the OA policy in SKILL.md)
uv run scripts/europepmc_api.py search \
  "(single-cell RNA sequencing) AND (tumor microenvironment) AND (OPEN_ACCESS:y OR OPEN_ACCESS:n)" \
  --max_results 25 --sort "CITED desc" \
  --output /path/tmp_litsearch/europepmc.json

# OA-only sweep — omit the suffix
uv run scripts/europepmc_api.py search "CRISPR cancer" \
  --max_results 25 --output /path/tmp_litsearch/europepmc_oa.json

# DOI / PMID lookup
uv run scripts/europepmc_api.py search "DOI:10.1038/s41586-021-03819-2" \
  --output /path/tmp_litsearch/paper.json
uv run scripts/europepmc_api.py search "EXT_ID:34265844 AND SRC:MED" \
  --output /path/tmp_litsearch/paper.json

# Full text (plain text or JATS XML) and PDF
uv run scripts/europepmc_api.py get_fulltext PMC8371605 --output /path/tmp_litsearch/ft.txt
uv run scripts/europepmc_api.py get_fulltext PMC8371605 --format xml --output /path/tmp_litsearch/ft.xml
uv run scripts/europepmc_api.py download_pdf PMC8371605 --output /path/tmp_litsearch/paper.pdf

# Citation graph
uv run scripts/europepmc_api.py get_citations MED 34265844 --page_size 25 \
  --output /path/tmp_litsearch/citing.json
uv run scripts/europepmc_api.py get_references MED 34265844 --page_size 100 \
  --output /path/tmp_litsearch/refs.json
```

Subcommand arguments: `search <query> --output <f> [--max_results N (max 1000)]
[--result_type core|lite] [--cursor <mark>] [--sort "<field> desc>"]`;
`download_pdf <pmcid> --output <f>`; `get_fulltext <pmcid> --output <f> [--format text|xml]`;
`get_citations|get_references <source> <article_id> --output <f> [--page N] [--page_size N]`.

`source` is one of `MED` (PubMed), `PMC`, `PPR` (preprints), `PAT` (patents).
`search` output is `{hitCount, nextCursorMark, results[]}`; each result carries
`isOpenAccess`, which is what you annotate the merged list with.

Europe PMC search syntax: `DOI:`, `EXT_ID:… AND SRC:MED` (PMID), `AUTH:surname initials`,
`TITLE:`, `JOURNAL:`, `PUB_YEAR:2024`, `FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]`,
`HAS_FT:y`, `OPEN_ACCESS:y|n`, and `AND`/`OR`/`NOT`.

🔴 Confirm before bulk PDF/full-text retrieval, before adding a date window
(any scope narrowing), and before concluding a zero-result query means the
literature is absent.

---

## bioRxiv / medRxiv — fresh preprints only

Skill: `~/.claude/skills/literature-search-biorxiv/`
Run from: `~/.claude/skills/literature-search-biorxiv`

```bash
cd ~/.claude/skills/literature-search-biorxiv

# By DOI (the reliable path)
uv run scripts/search_by_doi.py --server biorxiv \
  --doi "10.1101/2023.08.15.551388" --include_abstracts \
  > /path/tmp_litsearch/biorxiv_item.json

# By date window — category REQUIRED, window ≤ 4 weeks
uv run scripts/search_by_dates.py --server biorxiv \
  --start_date 2024-01-01 --end_date 2024-01-14 \
  --category neuroscience --keywords "astrocyte" "glia" --match_logic OR \
  > /path/tmp_litsearch/biorxiv.json
```

Flags: `--server biorxiv|medrxiv` (default `biorxiv`), `--start_date`, `--end_date`,
`--category`, `--keywords` (list), `--match_logic AND|OR`, `--author`,
`--include_abstracts`. Records carry `doi`, `title`, `authors`, `date`, `category`,
`abstract` (stripped unless `--include_abstracts`), `published`.

**Anti-pattern — the #1 way this backend fails:** never widen the date range to
months or years hoping keyword filtering will find something. The API has no
server-side keyword search, so the script downloads the entire range's metadata and
filters in Python. Wide ranges mean thousands of calls, timeouts, and an API block.

**Measured cost, so you can size the window honestly.** On `ecology`:

| Window | Downloaded | Pages | After category | After keywords |
|---|---|---|---|---|
| 1 week | 1,490 records | 50 | 59 | 6 |
| 3 weeks | still fetching | >12 | — | — |

The 1-week run took minutes, not seconds. The "≤ 4 weeks" ceiling above is the
API's tolerance, **not** a practical budget — for a busy category use **1 week**.
It is also why this backend is for deliberate recency sweeps, never for topical
discovery. Watch the `[Page N] Fetched M/N papers...` lines on stderr to tell
progress from a hang.

Biology-relevant bioRxiv categories (the full 27 are in the backend's `SKILL.md`):
`ecology`, `evolutionary_biology`, `zoology`, `plant_biology`, `microbiology`,
`genomics`, `genetics`, `molecular_biology`, `cell_biology`, `neuroscience`,
`immunology`, `bioinformatics`, `systems_biology`, `paleontology`, `biophysics`,
`developmental_biology`, `cancer_biology`, `synthetic_biology`,
`animal_behavior_and_cognition`.

bioRxiv cannot download PDFs — for that, resolve the DOI to a PMCID via Europe PMC
and use `download_pdf` there.

---

## Not wired in

`literature-search-arxiv` (`~/.claude/skills/literature-search-arxiv/`) is excluded
because its biology coverage is only the `q-bio` category. Wire it in manually if the
topic is quantitative biology, biophysics, or computational neuroscience.

---

## Troubleshooting — reproduced failures

These were all hit and diagnosed while building this skill. Each one looks like a
different problem than it is.

### A backend hangs with no output and no error

Overwhelmingly the cause is an **orphaned process from an earlier run**, not a slow
API. Every backend CLI runs under `uv run` (a parent) and rate-limits through
`polite_http`, which enforces its limit **across processes** via a lock file per
host (`%TEMP%\polite-http-<host>.lock`). Kill only the wrapper — a `timeout`, a
stopped background job, a closed terminal — and the child `python.exe` survives,
still holding that host's slot. Every later call to that backend queues behind the
orphan and hangs silently.

Measured: a Europe PMC search hung past a 100 s timeout with nothing on stdout or
stderr. After killing the orphans, the identical command finished in **3.5 s**.

```bash
# Find them
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {
  \$_.Name -match '^(uv|python)\.exe\$' -and
  \$_.CommandLine -match 'europepmc_api|pubmed_api|search_by_dates'
} | Select-Object ProcessId,Name,CommandLine"
```

Kill those exact PIDs and retry. Also check for a surviving wrapper *script* — a
`run.sh`-style driver can outlive a stopped job and keep respawning children, which
makes it look like the orphans are self-repairing.

**Prevention:** run backend calls in the background and let them finish. If you must
abandon one, kill the process tree.

### The merge output shows `&lt;i&gt;…&lt;/i&gt;` inside titles

Europe PMC escapes its inline JATS markup, so a title arrives as
`… Detection of &lt;i&gt;Cladocopium thermophilum&lt;/i&gt; …`. Anything that strips
`<…>` tags before decoding entities leaves the literal `i` / `/i` behind.
`merge_results.py` decodes entities first, then strips tags (`clean_text`). If you
change that function, keep the order.
