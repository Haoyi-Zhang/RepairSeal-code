# Natural-source correspondence

Two source-selected Codeflaws pairs connect complete input/output C programs
with explicit project-authored scalar requests. They are not a random sample
or a repair-generation campaign. The original 380-request core and 400-request
grammar populations are unchanged.

## Evidence

| Record | Meaning |
|---|---|
| `source-admission.json` | All 600 source-member occurrences named by the frozen 300-pair index; 588 submission filenames and 582 byte contents are distinct. Zero original complete programs enter the unsigned scalar grammar. |
| `requests.json` | Four project-authored normalizations, two candidate versions per case, with 64 points each. |
| `model-outcomes.json` | Full, direct, and task-derived arithmetic outcomes; two accepts and two refutations, with counted work of 4,352 cells in each full-domain arm. |
| `certificates/` | Four full-vector packets and the two compact refutations of normalized requests. Their source bindings refer to those scalar requests. |
| `native-observations.csv` | 256 whole-program observations on the predetermined axes, all matching their own scalar models, including incorrect original outputs. |
| `existing-test-selection-status.json` | Frozen selected slots and validity/availability; no replacement after observing a payload or outcome. |
| `existing-test-observations.csv` | 48 executions on 24 existing input/output pairs across two versions. Expected-output bytes and native output values from those tests are omitted; match/status fields are derived records. |
| `test-selection.json` | Up to eight input member names per case and split, in lexical order. |
| `timing.csv` | 30 alternating-order paired repetitions per request, after two warmups of each measured workflow. |
| `compiler.json` | Actual frontend identity, target-width macros, compile options, and derived compile outcomes. Private directory prefixes are normalized. |
| `summary.json` | Actual environment, scientific source bindings, denominators, and completed native and model outcomes. |
| `source-binding-check.json` | The seven scientific source files did not change during the measured execution. |

Public source-binding keys use POSIX relative path spelling for portability;
the private Windows run's path separators are normalized without changing
their file digests or any scientific result.

For Watermelon, the original passes 4/5 selected repair tests and 8/8 selected
held-out tests; the supplied version passes 13/13 combined. For Toy Army, the
original passes 0/11 combined and the supplied version 11/11. The combined
ordinary tests therefore already distinguish both originals from their
repairs. The finite receiver supplies exhaustive verdicts and canonical
witnesses over the declared axes, not an observed additional detection gain.

The correspondence derivations are in
[`proofs/source-observation.md`](../../proofs/source-observation.md).
The task references establish positive even splitting and the three-turn
maximum, respectively. All chosen arithmetic intermediates fit the recorded
signed 32-bit target and the unsigned scalar model. Printed stdout, not the
zero process return, supplies the scalar observation. Native branch traces
were not instrumented; canonical traces remain kernel-relative.

## Reproduction and measurement boundary

From the artifact root, the offline path is:

```bash
python -B tests/test_codeflaws_cases.py
python -B tests/codeflaws_source_study.py --output /private/new-model-output
```

The CLI requires a new or empty output directory. To inspect the fixed external
archive and opt into only the four reviewed sources, follow the
[root instructions](../../README.md#external-archive-retrieval-and-identity-gate).
Neither the archive nor its source/test payloads, toolchain, native binaries,
or raw diagnostic streams are included here. The public packets contain only
project-authored scalar code. The exact identities gate execution of the
reviewed complete translation units, rather than arbitrary archive programs.

API timing starts with decoded requests and an existing full packet where
applicable. Construction-to-result timing separately includes automated
request construction/encoding, decoding, receiver work and result encoding;
the full arm also includes certificate production, packet encoding, a separate
receiver request decode, and packet decode. Manual source inspection and
normalization remain untimed, and no network transfer is measured. Count
callbacks run in separate untimed passes. Same-point compact/direct checking
starts with an already discovered claim and proves an existential violation;
it does not prove acceptance or leastness and is not timed as free discovery.

Timings describe the actual environment and inputs in `summary.json`; they
are not a portable speed law or a frontend-cost measurement. The full/direct
cell counts are equal under matching finite acceptance and least-witness
obligations.
