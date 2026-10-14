# Generator-Independent Semantic Certificates

This artifact accompanies **Source-Bound Semantic Certificates for Finite Program-Repair Checking: Full-Vector Work Equivalence and Compact Refutations**.

OpenAI Codex assisted manuscript revision, implementation and test development,
and review of the ordinary arguments. Measurements come from executed artifact
workflows; the current complete-JSON receiver is not a streaming implementation.

## Supported scope and results

The command-line interfaces decode JSON as UTF-8, including receiver-owned
request identifiers. `python -B tests/test_cli_utf8.py` checks both receivers
and the full-vector producer with a non-UTF8 default. It does not broaden the
ASCII program language or add a native execution population.

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
| Owned nested source-occurrence conformance | 5 portable tests; 5 requests x 64 points = 320 candidate-point observations |

The exact negative result is central: full-vector checking and a certificate-free memoized topological evaluator perform the same number of local semantic-cell operations. The format supplies auditable source-bound evidence, not semantic-work reduction or an end-to-end speedup. The compact format obtains a real reduction only by certifying the weaker existential rejection claim.

The full-vector checker prepares input positions and verified child-vector
addresses once per reconstructed node, rather than rebuilding them at every
cell. It still computes, counts, type-checks and compares every cell, including
unreachable branches. `python -B tests/test_prepared_cells.py` checks literal
unsigned/Boolean formulas for all 24 circuit tags, trace-first diagnostics,
cell-value/type rejection counts, the 4,096-point boundary, the retained 380
full certificates and the unchanged certificate-rebuild contract. This is a
bounded implementation regression, not a new finite-domain theorem or a
claim that full-vector checking beats the certificate-free baseline.

The 400 grammar-generated requests use a separate AST generator and interpreter and were added after the fixture and stress populations were frozen. They probe template-overfitting risk but are post hoc, synthetic, and not a public-program sample.

The corrected selector budgets three small values separately from the mandatory
boundaries 31, 32, 2^31-1, 2^31, and 2^32-1. Every axis has eight distinct words;
all five boundaries occur on all 1,217 axes. The same 400 seeds now cover 657,728
input points and 47,327,168 cells in each full-domain receiver arm. The earlier
append-then-truncate selector discarded large boundaries; its smaller-domain
results are not the evidence for these counts. `holdout-differential/` retains
the corrected requests, results, seeds, and v3 summary.

The grammar AST interpreter assigns source-if sites in preorder across both
branches before executing the selected path. Skipped branches do not renumber
later sites, and separate source occurrences remain distinct even if they reuse
one AST object. The portable owned regression is:

```bash
python -B tests/test_nested_trace_repair.py
```

The suite has five test methods. Its unsigned saturation example uses five
program variants over 64 explicit points each, totaling 320 candidate-point
observations, not 320 programs. The axes include UINT_MAX and
the five mandatory boundary values. A literal arithmetic/trace oracle checks
the AST interpreter, the concrete receiver, full-vector checking, topological
direct evaluation and compact refutations for an unrepaired candidate, a correct
repair, overfit and preservation controls, and an interpreted definedness fault.
Additional controls cover skipped branches, shared AST occurrences, undefined
guards and rejected runtime-renumbered traces. These are owned finite semantic
regressions; they execute neither native C nor public benchmark programs.
`results/nested-source-occurrences/` retains the raw report, literal/AST/concrete
observations for all 320 candidate-point pairs, five separate receiver requests,
and scientific provenance. Source-if sites are zero-based and local to each
program role: the outer site is 0, then-branch site 1, else-branch site 2, and the
following guard site 3. A skipped branch does not close the gap in a trace.
Full and topological direct checking each perform 10,880 cells across the five
requests. Four authentic compact refutations verify; a forged refutation of
the correct repair and a runtime-renumbered trace are rejected.

To regenerate a scientific report at a new output path:

```bash
python -B tests/test_nested_trace_repair.py --report ../nested-report.json
```

`results/boundary-selection/receiver-timing.json` retains a fresh, descriptive
Windows/Python 3.12.14 comparison on the same 20 correct fixtures: ten paired
repetitions with alternating method order, 200 samples per method. Full/direct
median API-call times are 1.109/0.977 ms and the median paired ratio is 1.142;
both arms check the same acceptance obligations and 45,198 cells. Decoding,
I/O, and production are excluded. This rerun does not replace the historical
container timings or compare the unequal full/compact guarantees.

The separate `results/nested-source-occurrences/receiver-timing.json` retains
another same-obligation paired Windows/Python 3.12.14 measurement on those
20 correct fixtures, with ten alternating-order repetitions and 200 samples
per method. Full/direct median API-call times are 1.135/0.979 ms and the median
paired ratio is 1.153; both arms use 45,198 cells. Reconstruction and hashing
remain inside the timed calls; decoding, I/O, and production are excluded.
The result is certificate overhead on equal acceptance obligations, not a
compact/full speed comparison. Both earlier timing records remain unchanged.

`results/bounded-receiver-replay/` supplies a portable raw replay of all 380
retained full packets against literal oracles and the same-information direct
path, with 285 authentic compact results, the five boundary and five
prepared-cell test methods, and current source bindings for the 400 grammar
inputs. The full/direct total remains 1,179,684 cells per arm; the 20 accepted
fixtures remain 45,198 per arm. The grammar source/axis check is not a new
400-case semantic campaign. Regenerate this packet at an unused directory with
`python -B tests/bounded_closure_report.py --output ../bounded-replay-new`.
Actual runtime and source bindings are in its `environment.json`.

The same replay also runs three UTF-8 command-line identity controls and one
optimized-driver control, for 14 portable methods in total. The latter refuses
direct optimized execution of the scientific driver before output allocation
or campaign launch, keeping its assertion-based evidence comparisons active.
It is an owned launch control, not a compiler execution or new repair case.

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
The grammar campaign, retained disk replay, and receiver timing driver also run
with standard Python on Windows; unavailable POSIX peak RSS is recorded as null,
not as a measured zero. The full native/compiler reproduction remains Linux-only.
Scientific reconciliation permits different compiler installation paths and
version banners, including the compiler executable at command argument zero.
Both retained and newly measured provenance records are preserved unmodified.
Frontend roles, C11/O0 options and all remaining command arguments, return codes,
counts, source/harness bytes, and expected/observed outputs must still agree.
This is a scientific-result comparison, not a claim of identical environments.
Budget time/RSS measurements may differ; counted work, category counts and
worker counts remain part of the scientific comparison.

The retained v2 security receipt labels its malformed-JSON rejection `JSON
syntax`; the current receiver reports `JSON decoding` after controlled decoder
exception mapping. Reconciliation permits only that exact historical diagnostic
transition. Every case, rejection status, other reason, count, operator record
and import boundary must still agree. Neither receipt is rewritten. The
receipt-only comparisons and mocked JSON exceptions can be checked without
running the security generator or any campaign:

```bash
python -B tests/test_json_error_mapping.py
```

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

Boundary-selection regressions and the paired timing experiment can be run
without native C execution:

```bash
python -B tests/test_boundary_selection.py -v
python -B tests/receiver_timing.py --output ../paired-receiver-timing.json
```

The timing output must not already exist. A standalone corrected grammar run
uses `python -B tests/holdout_differential.py --output ../grammar-results --cases 400`;
its output directory must be new or empty.

Set `P004_TEST_TMP` to an existing isolated scratch directory to control where
temporary regression fixtures are created. Compiler-environment variants in
these tests are synthetic fixtures, not new native compiler measurements.
`.github/workflows/scientific-checks.yml` runs these regressions and the complete
offline scientific reproducer on Ubuntu with Python 3.12, GCC and Clang. It uses
a fresh `RUNNER_TEMP` directory and uploads raw run outputs, including actual
compiler provenance, on success or failure. CI timings are measured by the run;
the workflow's 20-minute timeout is a ceiling, not an estimated duration.
The compiler cross-check in this core workflow uses the project's authored
fixtures, not third-party native programs. The optional Codeflaws source study
below is separate: CI neither downloads its archive, runs upstream scripts,
nor compiles or executes third-party source.

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

- The corrected 400 grammar requests use exactly 64, 512, or 4,096 points: 125, 133, and 142 requests respectively. Their canonical circuits range from 13 to 148 nodes, with median 70. Full-certificate sizes range from 8,985 to 3,028,245 bytes, with median 206,909.5 bytes.
- The full-vector producer now computes one topological table per point. On a retained 48-term chain (53 nodes, 3 points), it records 159 vector cells; a legacy root-by-root diagnostic traversal records 3,558 recursive visits, while certificate bytes remain identical.
- An isolated 1,500-term left-deep addition has 3,034 characters, 3,009 tokens, 2,999 AST nodes, and depth 1,500. A diagnostic bypass reaches `RecursionError`; production producer/full/compact paths all reject on `AST depth`. An 11-digit literal is rejected on `literal length`. No wrong acceptance is claimed.
- `(x == 0u) || ((1u / x) > 0u)` is semantically defined on `{0,1,2}` by short circuit, but the current selector-definedness simplifier cannot prove direct `true`; producer and both checkers reject it consistently.

## Trust and independence boundary

The receiver validates schemas and limits, computes source bindings, reparses source, reconstructs canonical topology, and checks evidence. Request JSON preserves the insertion order of the receiver-owned `inputs` map; certificate key sorting is not allowed to redefine that order. The producer and both checkers enforce actual AST depth/node limits before recursive elaboration and check literal digit length before integer conversion. A mathematically total selector is admitted by this prototype only when its reconstructed definedness simplifies directly to Boolean `true`; this is an explicit conservative completeness boundary. The full-vector checker imports no producer module. The compact checker reuses receiver-owned parser/circuit code and imports neither producer. The proofs are manual conditional arguments, not proof-assistant derivations. Differential, native, boundary, and mutation testing reduce implementation risk but do not mechanically prove the receiver.

## Codeflaws boundary

`public-data/` freezes 300 unique rows from a pinned official Codeflaws
defect-detail index: 284 `WRONG_ANSWER`, 9 `RUNTIME_ERROR`, and 7
`TIME_LIMIT_EXCEEDED` records over 181 contest identifiers. The original frozen
index audit used metadata only: it did not acquire or execute corresponding
source programs, and those 300 records are not 300 compiled, repaired, or
certificate-checked programs. A later, separately identified source study uses
a privately acquired official archive; it does not replace that historical
population or relabel its results.

### Optional offline source study

`tests/codeflaws_cases.py` contains project-authored mathematical normalizations
of two source-selected natural pairs from the frozen index:
`4-A-bug-18258406-18258457` and `84-A-bug-9385928-9385933`. Each pair contributes
its buggy and supplied versions, giving four requests on 64 points each.
Selection was structural, not random or based on held-out outcomes. References
come from the official task specifications, not the supplied outputs. The
study evaluates supplied versions; it does not generate repairs or estimate
benchmark-wide repair effectiveness.

The unchanged receiver's source audit covers 600 archive-member occurrences
across the 300 indexed pairs, with 588 distinct submission filenames and 582
distinct source contents. It admits zero original translation units. These
are unsupported-language admissions, not repair-correctness verdicts; the
four adapted requests do not count as original-source admission.

For model-only replay, Python and the bundled project files suffice:

```bash
python -B tests/codeflaws_source_study.py --output ../private-source-models
```

Use a new or empty output directory. This default mode performs no download,
archive inspection, C compilation, or native execution. It checks full-vector
and certificate-free topological results against the mathematical oracle,
records equal work (4,352 cells per arm across the four requests), and records
paired timings. Equal work does not establish a speedup. Compact
checking is compared with direct checking of the same supplied point/trace;
neither proves acceptance or leastness, and witness discovery is not free.
Source inspection and manual I/O/type mapping are separate, untimed construction
work, not an automated frontend or a zero-cost preprocessing stage.

### External archive retrieval and identity gate

Obtain the archive separately from the download link on the
[official Codeflaws site](https://codeflaws.github.io/), after assessing the
applicable rights and terms. Its advertised link is the unversioned
[NUS archive](http://www.comp.nus.edu.sg/~release/codeflaws/codeflaws.tar.gz);
the private acquisition used the corresponding
[HTTPS URL](https://www.comp.nus.edu.sg/~release/codeflaws/codeflaws.tar.gz).
Do not substitute the website's GitHub source ZIP/tarball, a partial download,
or another snapshot. Record the actual retrieval URL, date, byte count and
SHA-256 privately. No artifact command downloads this payload.

The reviewed archive is exactly 265,695,532 bytes with SHA-256
`2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11`.
The driver rejects any other size or digest before opening the tar stream.
This identifies the locally reviewed snapshot; the metadata Git commit is
not an archive release identifier or a distributor signature. Inside the
archive, the four reviewed whole-source identities are:

| Member below `codeflaws/` | SHA-256 |
|---|---|
| `4-A-bug-18258406-18258457/4-A-18258406.c` | `0713806f76a4bf8c22a3ee7ca6a2585b2d08e2073b02094f6c7337ec1d0c24df` |
| `4-A-bug-18258406-18258457/4-A-18258457.c` | `6f74c3b6969296535b12ca5393e781fa0c8ce783f1c40f2dd4d2247634c31486` |
| `84-A-bug-9385928-9385933/84-A-9385928.c` | `1686ffd63ba4033a98d5b3d6b96b8e28a89764b99ae523958191a99d68e56431` |
| `84-A-bug-9385928-9385933/84-A-9385933.c` | `c6cacf09a2c35fa5e4071b10e0cf1b361060f1bf62dcf57375b23ee2cec34c90` |

The driver checks these source digests and the complete 600-member cohort,
rejecting missing or duplicate source-member identities. To repeat only that
inspection and model replay, without running third-party code:

```bash
python -B tests/codeflaws_source_study.py --archive /private/codeflaws.tar.gz --output /private/source-inspection
```

### Explicit reviewed-only native opt-in

Native execution requires both `--execute-reviewed` and an explicit local
compiler, in addition to the exact archive. Only opt in after reviewing all
four complete translation units and their source-to-model correspondence:

```bash
python -B tests/codeflaws_source_study.py --archive /private/codeflaws.tar.gz --execute-reviewed --compiler /path/to/reviewed/cc --output /private/source-native
```

For an already installed, reviewed Zig compiler use its executable path and
add `--zig`; the study does not install a toolchain. Compilation is serial,
uses C11/O0 and an isolated private working directory, and runs only the four
unchanged, digest-matched translation units. No upstream build/repair script
is run. This opt-in is not part of the core reproducer, release gate, or CI.

The native protocol compares decoded stdout with the corresponding model on
each 64-point domain (256 source-version/input observations). The 4A codec maps
exact `YES`/`NO` labels to 1/0 after stripping surrounding whitespace; the 84A
codec requires a single nonnegative decimal integer. Process status zero is
successful completion, not the scalar model output. Correspondence assumes
successful input/output and a 32-bit signed-`int` implementation; the driver
checks integer-width macros. On these legal inputs the relevant arithmetic
intermediates are nonnegative and at most 300,000,000, so the unsigned-32
normalization preserves the computation. It does not cover malformed inputs,
I/O failure, arbitrary signed C, or all legal task inputs. Certificate source
bindings and canonical branch traces refer to the normalized functions, not
directly to the original whole programs or measured native branch traces.

Existing repair and held-out tests are a separate comparison: up to the first
eight inputs per split/subject by lexical member name, selected before their
payloads are read, with no replacement or model tuning from held-out outcomes.
The current selection comprises 24 input/output pairs, each run on both
versions (48 test executions, not 48 distinct tests). Actual completion,
agreement, failures and timings must be read from the run's `summary.json`,
`native-observations.csv`, and `existing-test-observations.csv`; protocol counts
alone are not successful-run evidence.

Project-authored correspondence explanations and the derived records are in
[results/source-correspondence/](results/source-correspondence/), with the
measured current source bindings, four full packets and two compact packets.
Keep the archive, original source/test bytes, compiler, binaries and raw private
logs outside the deliverable. Publish only project-authored code/models and
derived data that do not reproduce upstream source or test payloads; check
serialized requests, certificates and logs as well as file extensions.

The bundled index's pinned repository provenance, its row-97 empty-tag
normalization, and the exact upstream MIT notice are documented in
[licenses/NOTICE.txt](licenses/NOTICE.txt) and
[licenses/Codeflaws-MIT.txt](licenses/Codeflaws-MIT.txt). That repository notice
does not establish an archive-wide license or rights from every Codeforces
contestant. Project licensing does not relicense upstream programs or tests.
