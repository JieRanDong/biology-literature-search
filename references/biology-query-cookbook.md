# Biology query cookbook

How to turn a biology question into a correct query on each backend. Every count
below was measured against the live APIs on 2026-09-17.

---

## 1. Species and taxonomy

**Use the scientific name, not the common name.** `Danio rerio[Organism]`
resolves through the NCBI taxonomy and picks up synonyms; `zebrafish` as free
text misses papers that only write the binomial.

| Backend | Species-scoped query | Result |
|---|---|---|
| pubmed | `Danio rerio[Organism]` | 67,990 |
| pubmed | `Danio rerio[tiab]` | 12,355 |
| pubmed | `zebrafish[MeSH Terms]` | 51,326 |
| pubmed | `Danio rerio[Organism] AND regeneration[tiab]` | 3,140 |
| europepmc | `Danio rerio` (free text) | 43,361 |
| europepmc | `ORGANISM:"Danio rerio"` | **151 — do not use** |

Europe PMC's `ORGANISM:` field is effectively unpopulated for this purpose.
Use free text there. PubMed's `[Organism]` is the reverse — undocumented in the
upstream skill but it works and is the strongest species filter available.

To combine a species with a biological process on PubMed, nest the tags:

```
("Danio rerio"[Organism]) AND ("Regeneration"[MeSH Terms] OR regeneration[tiab])
```

For a taxonomic sweep above species level (all amphibians, all teleosts), no
backend here has a clean rank filter. Approximate it by OR-ing representative
genera, or by naming several `[Organism]` terms:

```
("Anura"[Organism] OR "Caudata"[Organism] OR "Gymnophiona"[Organism])
```

---

## 2. bioRxiv category names

bioRxiv's subject categories are the cleanest enumeration of "生物大类" any of
these backends exposes — 27 categories covering the whole of biology. Pass
exactly one as `--category`.

**bioRxiv:** `animal_behavior_and_cognition`, `biochemistry`, `bioengineering`,
`bioinformatics`, `biophysics`, `cancer_biology`, `cell_biology`,
`clinical_trials`, `developmental_biology`, `ecology`, `epidemiology`,
`evolutionary_biology`, `genetics`, `genomics`, `immunology`, `microbiology`,
`molecular_biology`, `neuroscience`, `paleontology`, `pathology`,
`pharmacology_and_toxicology`, `physiology`, `plant_biology`,
`scientific_communication_and_education`, `synthetic_biology`,
`systems_biology`, `zoology`

**medRxiv** uses a separate list (addiction medicine, cardiology, infectious
diseases, oncology, psychiatry, public health, …) — see the upstream skill's
valid-categories section.

The categories the biomedical databases underserve — `ecology`,
`evolutionary_biology`, `zoology`, `plant_biology`, `paleontology`,
`animal_behavior_and_cognition` — are exactly the ones this backend covers
best. That is its main reason to exist in this pipeline.

---

## 3. Other query patterns worth knowing

**Gene / protein names.** PubMed indexes gene symbols and protein names
directly, but symbols collide with ordinary English (`SET`, `CAT`, `WAS`).
Anchor them: `"PRNP"[tiab] AND prion[tiab]`, or go through `[MeSH Terms]`.
For sequence- and structure-level work, use the dedicated `uniprot-database`,
`ensembl-database`, `pdb-database` and `ncbi-sequence-fetch` skills instead of
the literature backends.

**Cross-linking a paper to data.** Only the pubmed backend can do this
natively: `find_linked_biological_data "<pmid>" <db> <linkname>`. Verified
linknames:

| target db | linkname | gives you |
|---|---|---|
| `gene` | `pubmed_gene` | NCBI Gene records |
| `nuccore` | `pubmed_nuccore` | GenBank nucleotide sequences |
| `protein` | `pubmed_protein` | RefSeq / GenPept proteins |
| `pccompound` | `pubmed_pccompound` | PubChem compounds |
| `pcassay` | `pubmed_pcassay` | PubChem bioassays |
| `snp` | `pubmed_snp` | dbSNP variants |
| `clinvar` | `pubmed_clinvar` | clinical variants |
| `structure` | `pubmed_structure` | PDB structures |
| `sra` | `pubmed_sra` | raw sequencing data |
| `pmc` | `pubmed_pmc` | PMCID → full text |
| `pubmed` | `pubmed_pubmed_citedin` | forward citations |
| `pubmed` | `pubmed_pubmed_refs` | bibliography |

**Taxonomy and nomenclature papers** are the hardest case for all the backends
wired in here — many are in journals never indexed by MEDLINE or Europe PMC,
and predate DOI assignment. For pre-1990s systematic biology, no backend here is
complete; treat a low hit count as a coverage limit, not as evidence of
absence.

**Not covered here.** If the user turns out to need cross-disciplinary breadth
(funding data, institution-level bibliometrics, every journal in every field),
that is the `literature-search-openalex` skill used on its own — it is not part
of this pipeline because its CLI needs an OpenAlex API key to be usable.

---

## 4. Absence is not evidence

A zero or near-zero result has two causes that look identical: a malformed
query, and a genuine gap. Before reporting "no literature exists":

1. Re-run the query with the discipline filter removed entirely.
2. Try the other backends — each has different coverage and tokenisation.
3. Check the species/term spelling with `verify_medical_spelling` (pubmed).
4. Quote the exact query string and its `hitCount` in the answer.

Never widen a date window or drop a concept silently to manufacture a hit.
