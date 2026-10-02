# Conditional soundness of the finite semantic proof DAG

## Objects

Let the receiver fix original program `P`, candidate `Q`, reference `T`, a semantically total repair guard `R`, ordered variables `(x1,...,xn)`, and finite sorted domains `D1,...,Dn`. The declared domain is the Cartesian product `D`. The executable prototype admits a conservative subset: the independently reconstructed guard-definedness term must simplify directly to Boolean `true`; certificate fields never determine this admission decision.

For each role and input, source execution yields definedness, a value when defined, and a source-if trace. The obligations are candidate definedness, reference agreement under `R`, and original preservation under `not R`.

The proof certificate contains a canonical typed acyclic circuit and a semantic vector for every node over the receiver-generated point order.

## Lemma 1: vector induction

Assume exact topology reconstruction and successful local checking. Induct over node ID.

- A constant vector is checked against its constant.
- An input vector is checked against the corresponding coordinate of every canonical point.
- Every compound node refers only to earlier nodes. By induction, child vectors equal their denotations. The local rule checks the parent as the declared total operator applied to those child cells.

Therefore every checked vector equals the denotation of the independently reconstructed node at every declared point.

## Lemma 2: source-to-root correspondence

Assume the independent parser and compiler implement the documented fragment semantics. Structural induction over expressions and statements gives:

- output roots equal source returned values on defined executions;
- definedness roots are true exactly when the admitted source execution is defined;
- event reach/guard roots reconstruct the source-if trace, including prefixes terminated by undefinedness.

Exact root binding prevents the producer from substituting another observation.

## Theorem: generator-independent soundness

If the checker returns `ACCEPT`, then all three obligations hold at every point in `D`, independently of how the candidate or certificate was generated.

**Argument.** Acceptance requires a completely locally valid certificate. Lemma 1 establishes every obligation-root vector cell. Lemma 2 connects those roots to the authoritative sources. The canonical point list enumerates all of `D`. Acceptance checks every obligation cell as true.

## Refutation and least witness

If a checked obligation vector contains false cells, each names a real violation. The checker chooses the first failing obligation and minimizes candidate trace then input over every false point, so the returned witness is the least under the declared total order.

## Finite format completeness

For every prototype-admitted request, a valid certificate exists: use the canonical reconstructed circuit and evaluate every node at every canonical point. Valid evidence may lead to either `ACCEPT` or `REFUTED`; evidence validity is distinct from patch correctness. This is not completeness for all mathematically total selectors: selectors whose definedness is total only through a short-circuit argument that the current simplifier cannot reduce are conservatively rejected.

## What is not proved

- The Python checker is not mechanically verified.
- The theorem is conditional on parser/compiler/local-rule correctness.
- The finite domain is not all 32-bit inputs.
- The language is not full C.
- A proof-DAG operation reduction does not imply elapsed-time speedup.
- Hash collision resistance and the host runtime are environmental assumptions.


## Strong-baseline correction

The original recursive comparison is not evidence of certificate-induced work reduction. A memoized topological evaluator that receives no certificate performs exactly one operation per node--point cell, equal to the full-vector checker under the same counting convention. The 309,582 count is internal recursion inside a certificate-rebuild diagnostic that also performs 45,198 outer proof-cell checks; it is not the certificate-free `Session/direct_result` timing arm. The 6.85x ratio therefore measures repeated recursion only. See `refutation-boundary.md` for the exact work-equivalence proposition and the separate one-point refutation theorem.
