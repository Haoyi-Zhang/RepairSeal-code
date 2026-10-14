# Owned nested source-occurrence conformance

Five portable test methods pass. Five owned unsigned-saturation request variants
use the same ordered `(x,y)` axes
`[0,1,3,31,32,2147483647,2147483648,4294967295]`: 64 points per
request and 320 candidate-point observations in total, not 320 programs.
The literal oracle uses direct arithmetic and fixed source sites without parsing
emitted C. The AST interpreter and concrete receiver are compared at every point.
Full-vector and certificate-free topological checking also match the literal
status and canonical witness for all five requests, with 10,880 cells per arm.

| Variant | Result | Obligation | Canonical input (x,y) | Full/direct cells |
|---|---|---|---|---:|
| unrepaired | REFUTED | repair | (4294967295,0) | 1856 |
| correct | ACCEPT | none | none | 1856 |
| overfit | REFUTED | repair | (4294967295,3) | 2176 |
| regression | REFUTED | preserve | (2147483648,0) | 2240 |
| defined | REFUTED | defined | (4294967295,0) | 2752 |

Site IDs are zero-based structural occurrences local to each source role.
An if is visited before its then-subtree, else-subtree, and following statement.
Both branches are numbered before path selection; object reuse does not identify
two source occurrences. In these requests the outer, then-nested, else-nested,
and following guard sites are 0, 1, 2, and 3. At (1,1), the unrepaired candidate
returns 2 with trace `[[0,0],[2,1],[3,0]]`. Compact checking rejects a witness
whose authentic site IDs are replaced by runtime event ordinals. Undefined
guards emit no decision, and no event follows the first undefined operation.
Four authentic compact refutations verify; an attempted refutation of the
correct repair is rejected.

- `report.json`: raw v2 test result, method names, five embedded requests,
  all 320 literal/AST/concrete observations, full/direct outcomes, and compact
  refutations or accepted-request misuse rejection.
- `inputs/`: the five authoritative receiver requests, with input insertion
  order preserved. Each is identical in content to its embedded report request.
- `provenance.json`: axes, source-site convention, oracle and receiver entry
  points, test scope and execution boundaries.
- `receiver-timing.json`: a separate same-obligation measurement on the
  existing 20 correct fixtures, not on the five nested requests. Ten paired
  alternating-order repetitions yield 200 samples per method. Full/direct
  medians are 1.135/0.979 ms and median paired ratio is 1.153; both arms perform
  45,198 cells. Decoded-input API calls include reconstruction and hashing,
  excluding decoding, I/O and certificate production. Earlier timing files are
  unchanged; this descriptive ratio is not a cross-platform law.

From the artifact root, generate a report at an unused output path:

```bash
python -B tests/test_nested_trace_repair.py --report ../nested-report.json
```

These are owner-authored interpreted finite semantic tests. No native C or
third-party source is executed. The definedness variant is interpreted data;
it is not a native undefined-behavior test. Historical native fixture evidence
is separate. The retained 380-request core and 400-request grammar campaign
counts remain unchanged, and Codeflaws remains a metadata-only index audit.
