# Certificate formats

All certificate JSON is parsed with duplicate-key rejection and rejection of non-finite constants. Semantic objects are closed-world: extra fields are invalid. Integer fields reject JSON booleans.

## Receiver-authoritative request order

The request, not a certificate, owns coordinate order. The request's `inputs` object is serialized with insertion order preserved and is strict-loaded from disk. Certificate `input_order`, `domains`, and point tuples are checked against that order; they never define it. Certificate bodies may use canonical sorted-key JSON for hashing only after receiver-owned coordinate order has been fixed explicitly.

The prototype also distinguishes mathematical selector totality from executable admission. A selector can be semantically defined at all declared points by short-circuit evaluation, yet be rejected if its reconstructed definedness does not simplify directly to Boolean `true` under the current simplifier. The producer and both checkers apply the same conservative admission rule.

## `finite-semantic-proof-dag-v1`

The full-vector certificate binds the request identifier, word width, ordered domains, authoritative source hashes, canonical points, canonical circuit nodes, role roots, obligation roots, and an outer SHA-256 digest. Each node stores its operation, children, result sort, and complete vector over the canonical point order. The receiver reconstructs the expected circuit from source and requires exact structural equality before validating each local vector cell.

Canonical construction elaborates original, candidate, and reference in that order, then the repair guard and the three safety-aware obligations. It then materializes the value-only repair and preservation ablation expressions, in that order, retaining every interned node. These additional expressions are not trusted obligations. The receiver-owned `Circuit`, `Elaborator`, and `build_expected` definitions in `src/proof_dag_checker.py` specify the exact interning, folding, traversal, and operand order for byte conformance.

This format can support universal acceptance and canonical counterexample selection because it covers the complete finite domain. It is not a compressed symbolic proof: completed checking of a locally valid certificate and memoized topological direct evaluation both visit every node--point cell exactly once. The checker computes expected local values and compares submitted cells; malformed or inconsistent evidence can reject early. The current producer also constructs vectors topologically once per point; a retained chain regression confirms byte-identical certificates relative to a legacy recursive construction while eliminating repeated root traversals.

## `finite-semantic-refutation-v1`

The compact format contains exactly:

- `kind`;
- `request_id` and `word_bits`;
- `input_order` and complete `domains`;
- `source_sha256` for original, candidate, reference, and repair guard;
- one `obligation`;
- one in-domain `input`;
- one exact candidate `trace`; and
- `certificate_sha256` over all preceding fields.

The receiver reparses and semantically evaluates the bound sources at only the claimed point. It validates request fields and the product bound without allocating the Cartesian point list, then checks exact point type/arity and each coordinate's membership in its receiver-owned axis. This is equivalent to product membership. Axis validation and membership still contribute to total cost; semantic work remains N circuit cells. Full-vector validation continues to enumerate canonical points. Acceptance proves that the named obligation is false there and that the trace is authentic. It proves neither leastness nor acceptance of any other point. The checker rejects this format for a true claimed root, malformed traces, altered sources or domains, stale or recomputed malicious bindings, and extra fields.

Canonical certificate JSON uses UTF-8, sorted keys, no insignificant whitespace, and no NaN or infinity. Authoritative request serialization is the exception to sorted-key output because input insertion order is semantically binding.
