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
- 300 Codeflaws index rows for the original provenance and defect-taxonomy audit
  only; that frozen campaign did not acquire or execute the corresponding
  public source programs. The later optional source study below is separate.

Every frozen structured request has four inputs with three values each, hence 81 canonical points. Corrected grammar-differential requests have exactly 64, 512, or 4,096 points (125, 133, and 142 requests) and 13--148 canonical nodes with median 70. Each axis retains three small values plus five fixed boundaries, reaching the admitted 4,096-point cap for four inputs. The fixed 81x one-point/full-vector cell ratio is reported only for the 285 refuted requests in the frozen structured population, not as a universal property of the format.

All retained request files preserve receiver-authoritative input insertion order. The disk-replay gate strict-loads 780 requests and reconstructs the expected order from the real deterministic generators and seeds; certificate fields are never used as authority.

## Process budget

The integrated reproducer uses at most three concurrent local subprocesses and no nested worker pool. This remains below the four-core project ceiling. Individual stages have bounded timeouts. The project memory ceiling is 4 GiB. The corrected Windows grammar run records wall time but has no POSIX peak-RSS measurement; its null RSS field does not establish a measured memory high-water mark.

## Descriptive performance

The retained core run reports:

- repeated-correct medians: full proof 1.677 ms, topological direct 1.053 ms, certificate rebuild 5.290 ms, and certificate-free `Session/direct_result` 1.112 ms;
- all-request medians: full proof 2.741 ms, topological direct 1.550 ms, `Session/direct_result` 1.136 ms, and one-point refutation 0.486 ms.

These are environment-specific descriptive measurements, not portable performance bounds. The 309,582 count belongs only to the internal recursive phase of the certificate-rebuild diagnostic, which also performs 45,198 outer proof-cell checks; it does not correspond to the `Session/direct_result` timing. The decisive implementation-independent result within the stated counter model is 45,198 full-vector cells = 45,198 topological-direct cells.

Peak RSS, wall-clock time, and timestamps are regenerated and intentionally excluded from deterministic scientific-field comparisons.

## Optional Codeflaws source study

This is separate from the frozen core and its authored native harness. The
default `python -B tests/codeflaws_source_study.py --output ../private-source-models`
needs only Python and bundled project files: no network, archive, compiler or
third-party native execution. It replays four project-authored normalized
requests from two source-selected natural pairs on 64 points each. Full-vector
and certificate-free direct checking each use 4,352 cells. Manual source
inspection and I/O/type mapping are untimed work, not automated translation
or a measured zero-cost stage. Timings are descriptive, not a positive benefit
claim; same-point compact/direct comparison certifies only rejection.

Archive inspection additionally requires a separately obtained private copy
from the [official download page](https://codeflaws.github.io/). The reviewed
[NUS HTTPS archive](https://www.comp.nus.edu.sg/~release/codeflaws/codeflaws.tar.gz)
is 265,695,532 bytes, SHA-256
`2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11`.
The advertised HTTP URL is unversioned; the pinned metadata commit does not
version this tarball. The driver rejects any other size/digest and checks the
four complete source-member hashes listed in [README.md](README.md#external-archive-retrieval-and-identity-gate)
and `tests/codeflaws_cases.py`. No driver downloads the archive or runs upstream
scripts. The raw cohort has 600 member occurrences, 588 distinct submission
filenames and 582 distinct source contents; zero unchanged sources are admitted
by the receiver. Normalized model admission is not raw-source admission.

Only `--execute-reviewed --archive /private/codeflaws.tar.gz --compiler /path/to/reviewed/cc`
opts into compilation/execution; use a new or empty private `--output` directory.
Add `--zig` only when the explicit compiler is a reviewed Zig executable.
This requires review of the four whole translation units and correspondence,
not merely a matching hash. The implementation checks a 32-bit signed-`int`
target premise, compiles serially with C11/O0, uses an isolated private working
directory, and gives each program run a five-second timeout. It records compiler
identity, compile commands/return codes, domain observations, test identities
and test outcomes. Its existing-test payload limit is 256 bytes per member;
missing or invalid selected pairs are recorded separately and are not executed
or replaced by later tests.
These limits and timeouts are not a security sandbox for arbitrary source.

The declared-domain comparison covers four versions x 64 inputs = 256 native
observations. Existing tests are separate: the current lexical selection has
24 input/output pairs (48 executions across both versions). Both populations
require actual run records for success claims. The models assume successful
scalar input/output and compare decoded stdout, not `main`'s process return;
the selected arithmetic stays nonnegative and at most 300,000,000.
Certificate source bindings and traces belong to the normalized functions.

The optional archive/native study is not invoked by `reproduce_all.py` or
`release_gate.py`. CI runs only the offline model regressions and a one-repeat
model replay for these cases. It does not download this archive, execute
upstream scripts, or compile/run third-party native sources; its existing native
check uses project-authored fixtures only. Keep upstream sources/tests, archive, compiler,
binaries and raw private logs outside public outputs. The intended public
directory [results/source-correspondence/](results/source-correspondence/)
is reserved for project-authored explanations/models and derived data after
checking that no serialized source or test payload is embedded. Actual final
native and timing results come from populated run records there, not from the
protocol's intended counts. See [licenses/NOTICE.txt](licenses/NOTICE.txt) for
metadata provenance and the archive-versus-repository licensing boundary.
