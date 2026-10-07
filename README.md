# Generator-Independent Semantic Certificates

This artifact accompanies **Source-Bound Semantic Certificates for Finite Program-Repair Checking: Full-Vector Work Equivalence and Compact Refutations**.

## Supported scope and results

The implementation covers loop-free scalar 32-bit unsigned C over explicit finite ordered input domains. The receiver owns the original program, candidate, reference, repair guard, and three obligations: candidate definedness, repair-region agreement, and preservation outside that region.

Two evidence formats are implemented:

1. a **full-vector proof DAG**, checked after independent receiver parsing and canonical circuit reconstruction; and
2. a **compact one-point refutation**, which proves one actual violation and its candidate trace but cannot prove acceptance or leastness.

| Evidence | Result |
|---|---:|
| Frozen core requests | 380 (95 accepted, 285 refuted) |
| Exact-oracle status and canonical-witness agreement | 380/380 |
| Full-vector targeted corruptions rejected | 6,000/6,000 |
| Compact refutations verified | 285/285 |
| Compact corruptions rejected | 2,850/2,850 |
| Forged refutations of accepted requests rejected | 95/95 |
| Post hoc grammar-differential requests | 400 |
| Grammar oracle/topological agreement | 400/400 and 400/400 |
| Grammar compact refutations / rejected forgeries | 300/300 and 100/100 |
| Full proof / topological-direct cells on 20 correct fixtures | 45,198 / 45,198 |
| Certificate-rebuild diagnostic | 45,198 outer proof cells + 309,582 internal recursive visits; still receives the certificate |
| Full-proof cells across all 380 frozen-core requests | 1,179,684 |
| Median full / compact bytes on the same 285 refutations | 15,604 / 667 (ratio of medians 23.39x; median paired ratio 23.23x) |
| Median compact semantic-cell reduction | 81x on the retained 81-point requests |

The exact negative result is central: full-vector checking and a certificate-free memoized topological evaluator perform the same number of local semantic-cell operations. The format supplies auditable source-bound evidence, not semantic-work reduction or an end-to-end speedup. The compact format obtains a real reduction only by certifying the weaker existential rejection claim.

The 400 grammar-generated requests use a separate AST generator and interpreter and were added after the fixture and stress populations were frozen. They probe template-overfitting risk but are post hoc, synthetic, and not a public-program sample.

## Reproduce everything

Compact checking validates each claimed coordinate against its receiver-owned
axis after exact type and arity checks, without generating the Cartesian product.
This changes allocation and membership overhead, not the N-cell semantic work.
Full-vector checking still constructs the canonical points and checks NM cells.
`python -B tests/test_coordinate_membership.py` runs eight portable regression
groups: 552 complete product-reference/current comparisons, 8,644 finite
membership identities, 285 retained compact packets and 380 full packets.
The bounded result is retained in `results/coordinate-membership/correctness.json`.
The stored container timing table uses product-enumerating admission; it is not a
timing measurement of axis-membership admission.

Requirements: Python 3.10 or newer, GCC, Clang, and standard POSIX utilities. The retained native evidence records GCC 14.2.0 at `/usr/bin/x86_64-linux-gnu-gcc-14` and Clang 17.0.0 at `/usr/local/swift/usr/bin/clang-17`; the reproducer resolves available `gcc` and `clang` frontends, records their identities and commands, and requires two separate matching outputs. No network, model API, credentials, private cache, or paper directory is used.

The complete reproducer requires Linux (`resource` and `/proc` accounting).
Scientific reconciliation permits different compiler installation paths and
version banners, including the compiler executable at command argument zero.
Both retained and newly measured provenance records are preserved unmodified.
Frontend roles, C11/O0 options and all remaining command arguments, return codes,
counts, source/harness bytes, and expected/observed outputs must still agree.
This is a scientific-result comparison, not a claim of identical environments.
Budget time/RSS measurements may differ; counted work, category counts and
worker counts remain part of the scientific comparison.

```bash
python3 tests/reproduce_all.py --output ../replayed-results
```

The output directory must be absent or empty. The command reruns the replay-table negative baseline, two native compiler cross-checks, the 380-request study, 8,945 certificate negative controls, fail-closed security regressions, the 300-row Codeflaws index audit, the 400-case post hoc grammar differential, the producer-complexity regression, the AST/literal safety regressions, and the conservative-selector regression. It then performs a separate disk-replay audit: all 780 retained request files are strict-loaded; authoritative input order is recovered from the fixture/stress generators and retained grammar seeds, never from a certificate; 380 full-vector and 285 compact core certificates are replayed; and all 400 grammar results are revalidated.

For a dependency-closure and packaging check from a clean extraction:

```bash
python3 tests/release_gate.py
```

The release gate parses every Python file, rejects nested archives, caches, and generated checksum/inventory manifests, verifies required dependencies, and executes the complete reproducer. Its optional `--keep-output` accepts only a new or empty directory; an occupied directory or file is rejected without deletion. Without that option it creates and cleans up only its own temporary run, including on failure.

Portable comparison and output-safety regressions need only Python and do not
invoke a compiler or the Linux experiment drivers:

```bash
python -B tests/test_reproduction_contract.py
```

Set `P004_TEST_TMP` to an existing isolated scratch directory to control where
temporary regression fixtures are created. Compiler-environment variants in
these tests are synthetic fixtures, not new native compiler measurements.
`.github/workflows/scientific-checks.yml` runs these regressions and the complete
offline scientific reproducer on Ubuntu with Python 3.12, GCC and Clang. It uses
a fresh `RUNNER_TEMP` directory and uploads raw run outputs, including actual
compiler provenance, on success or failure. CI timings are measured by the run;
the workflow's 20-minute timeout is a ceiling, not an estimated duration.

## Important entry points

- `src/proof_dag_producer.py`: untrusted full-vector producer.
- `src/proof_dag_checker.py`: receiver parser, canonical DAG builder, full-vector checker, and strong topological baseline.
- `src/refutation_witness_producer.py`: compact witness packager.
- `src/refutation_witness_checker.py`: receiver one-point checker.
- `tests/structured_study.py`: frozen 380-request study and 8,945 negative controls.
- `tests/holdout_differential.py`: post hoc 400-case grammar/AST differential audit (the legacy filename is retained for evidence compatibility).
- `tests/disk_replay.py`: independent retained-file gate for 780 requests, 380 full certificates, 285 compact certificates, and 400 grammar results; it never trusts certificate coordinate order.
- `tests/edge_case_regression.py`: producer topological-reuse, left-deep AST/literal safety, and conservative selector-admission regressions.
- `tests/proof_dag_security.py`: malformed requests, strict JSON, type aliases, resource boundaries, and operator probes.
- `proofs/proof-dag.md`: conditional full-vector soundness argument.
- `proofs/refutation-boundary.md`: compact-refutation soundness and leastness boundary.
- `claim_evidence_ledger.csv`: claim-to-proof/code/input/result ledger.

## Audited structural ranges and edge regressions

- The 400 grammar requests use exactly 9, 27, or 81 points: 125, 133, and 142 requests respectively. Their canonical circuits range from 15 to 163 nodes, with median 69.5.
- The full-vector producer now computes one topological table per point. On a retained 48-term chain (53 nodes, 3 points), it records 159 vector cells; a legacy root-by-root diagnostic traversal records 3,558 recursive visits, while certificate bytes remain identical.
- An isolated 1,500-term left-deep addition has 3,034 characters, 3,009 tokens, 2,999 AST nodes, and depth 1,500. A diagnostic bypass reaches `RecursionError`; production producer/full/compact paths all reject on `AST depth`. An 11-digit literal is rejected on `literal length`. No wrong acceptance is claimed.
- `(x == 0u) || ((1u / x) > 0u)` is semantically defined on `{0,1,2}` by short circuit, but the current selector-definedness simplifier cannot prove direct `true`; producer and both checkers reject it consistently.

## Trust and independence boundary

The receiver validates schemas and limits, computes source bindings, reparses source, reconstructs canonical topology, and checks evidence. Request JSON preserves the insertion order of the receiver-owned `inputs` map; certificate key sorting is not allowed to redefine that order. The producer and both checkers enforce actual AST depth/node limits before recursive elaboration and check literal digit length before integer conversion. A mathematically total selector is admitted by this prototype only when its reconstructed definedness simplifies directly to Boolean `true`; this is an explicit conservative completeness boundary. The full-vector checker imports no producer module. The compact checker reuses receiver-owned parser/circuit code and imports neither producer. The proofs are manual conditional arguments, not proof-assistant derivations. Differential, native, boundary, and mutation testing reduce implementation risk but do not mechanically prove the receiver.

## Codeflaws boundary

`public-data/` freezes 300 unique rows from a pinned official Codeflaws defect-detail index: 284 `WRONG_ANSWER`, 9 `RUNTIME_ERROR`, and 7 `TIME_LIMIT_EXCEEDED` records over 181 contest identifiers. Corresponding source programs are not bundled or executed. No result represents those records as compiled, tested, repaired, or certificate-checked programs. This is the principal external-validity and venue-readiness limitation.
