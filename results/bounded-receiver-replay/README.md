# Portable bounded receiver replay

This raw packet records a portable Python replay of the retained owner-authored
finite corpus. It adds no programs to the frozen 380/400 populations and does
not replace earlier campaign bytes or timing measurements.

- `structured-replay.json` contains all 380 per-request literal-oracle,
  full-vector and certificate-free topological results, their authoritative
  input and certificate file bindings, coordinate order and axes, plus 285
  authentic compact results. Both full-domain arms perform 1,179,684 cells;
  the 20 accepted fixtures account for 45,198 cells per arm. Inputs remain in
  the public `proof-data/fixture-inputs/` and `proof-data/stress-inputs/`
  directories; they are not inferred from certificate fields.
- `boundary-tests.json` records the five existing boundary-selection methods.
- `prepared-cells.json` records the five existing prepared-cell methods and
  observed checks: 380 retained full packets, 1,179,684 retained full cells,
  20 literal formula cases / 3,392 cells, 48 local cell controls, three literal
  trace cases and the 4,096-point admission boundary.
- `grammar-source-check.json` binds all 400 existing grammar requests to the
  current seeded generator and its coordinate order. All five mandatory values
  occur on all 1,217 axes, totaling 657,728 points. This file checks source and
  boundary identity, **not** a fresh 400-case semantic campaign. Complete
  semantic outcomes remain in `proof-data/holdout-differential/`.
- `environment.json` records the actual Python/runtime/command and scientific
  source versions of this replay. Its environment does not describe historical
  native compiler or timing runs.

From the artifact root, use a new output directory:

```bash
python -B tests/bounded_closure_report.py --output ../bounded-replay-new
```

The separate `results/nested-source-occurrences/` packet retains five nested
requests and all 320 literal/AST/concrete candidate-point observations, with
zero-based source-preorder occurrence IDs (outer 0, then 1, else 2, later guard
3). It also retains the separate paired 20-fixture timing sample: median paired
full/direct 1.153 and 45,198 cells in both arms. The 81x full/compact cell ratio
instead compares universal/canonical checking with a weaker existential
one-point rejection contract. Neither comparison is a native C measurement.

No native compiler, public-source program, network target or external service
is executed by this workflow. The definedness cases are interpreted data.
Codeflaws remains a metadata-only index audit. Historical negative-control
campaigns (6,000 full, 2,850 compact, 95 accepted-request misuse rejections)
remain separate, unchanged evidence; this replay does not claim to rerun them.
