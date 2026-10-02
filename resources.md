# Resources and execution contract

## Required local tools

- Python 3.10 or newer; the core proof-DAG implementation uses only the standard library.
- Two independent C frontends available as `gcc` and `clang` for the retained native defined-value cross-check.
- Standard POSIX shell utilities.

The retained evidence was produced with:

- `/usr/bin/x86_64-linux-gnu-gcc-14`, `x86_64-linux-gnu-gcc-14 (Debian 14.2.0-19) 14.2.0`;
- `/usr/local/swift/usr/bin/clang-17`, `clang version 17.0.0 (https://github.com/llvm/llvm-project.git 10999b6d034fe318f3d56c83bddb6572593a8bb0)`.

Both compile `native-harness.c` with `-std=c11 -O0` to separate binaries and produce separate retained CSV files. The integrated reproduction records the resolved compiler paths, version first lines, exact compile/run commands, return codes, and 9,180 defined observations per compiler; it fails unless both outputs match the mathematical expected values and each other. Undefined candidate observations are excluded from native execution evidence.

The reproduction command performs no network access and invokes no language-model API. It creates temporary and replayed files only below the user-supplied output directory.

## Frozen populations

- 20 designed fixture families x 4 variants = 80 requests.
- 300 deterministic structured semantic-stress requests.
- 400 post hoc grammar-generated requests produced by a separate AST generator and interpreted by an independently written AST semantics.
- 300 Codeflaws index rows for provenance and defect-taxonomy audit only; no corresponding public source program is executed.

Every frozen structured request has four inputs with three values each, hence 81 canonical points. Grammar-differential requests have exactly 9, 27, or 81 points (125, 133, and 142 requests) and 15--163 canonical nodes with median 69.5. The fixed 81x one-point/full-vector cell ratio is reported only for the 285 refuted requests in the frozen structured population, not as a universal property of the format.

All retained request files preserve receiver-authoritative input insertion order. The disk-replay gate strict-loads 780 requests and reconstructs the expected order from the real deterministic generators and seeds; certificate fields are never used as authority.

## Process budget

The integrated reproducer uses at most three concurrent local subprocesses and no nested worker pool. This remains below the four-core project ceiling. Individual stages have bounded timeouts. The retained campaign runs well below the 4 GiB memory ceiling in the audited environment.

## Descriptive performance

The retained core run reports:

- repeated-correct medians: full proof 1.677 ms, topological direct 1.053 ms, certificate rebuild 5.290 ms, and certificate-free `Session/direct_result` 1.112 ms;
- all-request medians: full proof 2.741 ms, topological direct 1.550 ms, `Session/direct_result` 1.136 ms, and one-point refutation 0.486 ms.

These are environment-specific descriptive measurements, not portable performance bounds. The 309,582 count belongs only to the internal recursive phase of the certificate-rebuild diagnostic, which also performs 45,198 outer proof-cell checks; it does not correspond to the `Session/direct_result` timing. The decisive implementation-independent result within the stated counter model is 45,198 full-vector cells = 45,198 topological-direct cells.

Peak RSS, wall-clock time, and timestamps are regenerated and intentionally excluded from deterministic scientific-field comparisons.
