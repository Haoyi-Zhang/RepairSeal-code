# RepairSeal

This artifact accompanies *Source-Bound Semantic Certificates for Finite
Program-Repair Checking: Full-Vector Work Equivalence and Compact Refutations*.

OpenAI Codex assisted manuscript revision, implementation and test development,
and review of the ordinary arguments. Measurements come from executed artifact
workflows; the current complete-JSON receiver is not a streaming implementation.

## Scope

The receiver checks loop-free scalar unsigned-32 C over explicit finite ordered
input domains. It owns the original program, candidate, reference and repair
guard. The obligations are candidate definedness, agreement in the repair region
and preservation outside it.

The full-vector format is checked after independent parsing and canonical
circuit reconstruction. A compact one-point refutation checks one actual
violation and its candidate trace. It establishes rejection, not acceptance or
the least violating point. On equal full-domain acceptance obligations, full
checking and the certificate-free topological evaluator perform the same local
semantic-cell work. The one-point reduction corresponds to a different,
existential obligation.

## Setup and run

Use Python 3.10 or later. Portable receiver and comparison checks need only the
standard library. The complete resource-accounted campaign requires Linux, GCC,
Clang and standard POSIX utilities. Runners resolve and record the actual
compiler paths; no project command downloads a toolchain, dataset or model.

From this directory, use a fresh output directory outside the project:

```sh
python3 -B tests/reproduce_all.py --output /absolute/fresh/repairseal-run
```

This runs the replay-table baseline, two native compiler checks, the 380-request
study and 8,945 selected certificate controls, input/receiver regressions, the
300-row Codeflaws metadata audit, the corrected 400-request grammar differential
and the retained-file replay. The disk gate reloads authoritative requests and
recovers their input order from the generators and saved seeds, not certificates.
The output must be absent or empty. Failed commands and scientific mismatches
exit nonzero; diagnostic output remains available.

For the functional clean-extraction check, including that complete campaign:

```sh
python3 -B tests/release_gate.py
```

The gate checks dependency closure and packaged-file hygiene before execution.
Its optional `--keep-output` accepts a new or empty directory and preserves
caller-owned contents. Without it, the gate cleans only its own temporary tree.

## Focused checks and outputs

These portable commands avoid native compilation and the complete campaign:

```sh
python -B tests/test_cli_utf8.py
python -B tests/test_reproduction_contract.py
python -B tests/test_boundary_selection.py -v
python -B tests/test_nested_trace_repair.py
python -B tests/test_coordinate_membership.py
python -B tests/test_prepared_cells.py
```

The UTF-8 checks preserve receiver-owned identifiers under a non-UTF8 host
default. Comparison controls distinguish permitted environment telemetry changes
from scientific values and preserve occupied output directories. Boundary
selection keeps three small values plus all five mandatory unsigned boundaries.
Nested-source checks preserve preorder source-site numbering across skipped
branches and shared AST occurrences.

A portable retained-packet report can be generated separately:

```sh
python -B tests/bounded_closure_report.py --output /absolute/fresh/bounded-replay
```

That report rechecks 380 full packets, 285 authentic compact refutations and
the same-information direct path. It also checks grammar source/axis bindings;
it does not rerun the 400-request semantic campaign. Full native/compiler
reproduction remains Linux-only; unavailable Windows POSIX telemetry is null.

## Retained evidence

| Study | Result | Location |
|---|---|---|
| Frozen core | 380 requests: 95 accepted, 285 refuted | `results/`, `proof-data/structured-study.json` |
| Equal acceptance work | 45,198 cells per arm on 20 correct fixtures | retained study and paired receiver records |
| Core full checking | 1,179,684 cells per arm over all requests | `results/bounded-receiver-replay/` |
| Corrected grammar | 400 requests, 657,728 points; 47,327,168 cells per full-domain arm | `proof-data/holdout-differential/` |
| Nested source sites | Five owned requests, 320 candidate-point observations | `results/nested-source-occurrences/` |
| Selected mutations | 6,000 full, 2,850 compact, 95 forged-acceptance controls rejected | frozen study records |

The full/compact byte comparison concerns the same 285 refutations: median
sizes are 15,604 and 667 bytes. The 81-fold cell reduction on those 81-point
requests compares universal checking with one supplied violation, not equal
acceptance guarantees. Grammar inputs and mutation controls are constructed
tests, not independent public-program defects.

Paired measurements are retained separately by source/environment in
`results/boundary-selection/receiver-timing.json` and
`results/nested-source-occurrences/receiver-timing.json`. Both compare equal
acceptance obligations; the reported full/direct ratios exceed one. To run a
new, isolated measurement, inspect `tests/receiver_timing.py` and supply an
unused output file. Do not pool current allocation measurements with historical
container timings.

## Implementations and conditions

- `src/proof_dag_producer.py`: full-vector producer.
- `src/proof_dag_checker.py`: receiver parser, canonical circuit and direct baseline.
- `src/refutation_witness_checker.py`: one-point receiver.
- `tests/structured_study.py`, `holdout_differential.py`, `disk_replay.py`:
  core study, grammar differential and authoritative disk replay.
- `formats.md`, `proofs/`: schemas, local rules and conditional arguments.
- `resources.md`, `claim_evidence_ledger.csv`: resource protocol and evidence map.

The receiver checks exact schemas, source/domain/root bindings and every
required local semantic value. Resource bounds cover actual AST depth and node
counts; the current selector admission conservatively requires its definedness
to simplify to true. Manual proof arguments and separate checker code are
complemented by finite tests, not proof-assistant mechanization.

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
