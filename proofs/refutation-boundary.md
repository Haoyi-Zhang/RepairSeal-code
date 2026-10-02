# Compact refutation certificate: proof boundary

## Definitions

For a prototype-admitted request, the receiver constructs an ordered acyclic circuit `C`, an ordered finite domain `D`, three obligation roots, and the candidate trace events. A compact certificate names an obligation `o`, a point `d in D`, and a trace `t`, while binding all request fields and source texts by exact values and SHA-256 digests.

## Lemma 1: point-evaluation correctness

Assuming the receiver parser and local operator semantics implement the documented fragment, topological evaluation computes the denotation of every circuit node at the bound point. Proof: induction over the receiver-generated node order. Inputs and constants are immediate; every other node applies the documented local operator to already established children.

## Theorem 1: refutation soundness

If the compact checker accepts, then the named obligation is false at the bound point and the candidate trace equals the receiver-computed trace at that point.

Reason: before evaluating, the checker validates the closed schema, outer digest, request identifier, word width, ordered domains, input membership, and source digests. By Lemma 1 the obligation-root value is correct. Acceptance requires that value to be exactly Boolean false. The trace is recomputed from receiver-built reachability and guard nodes and compared with strict recursive type equality.

## Theorem 2: completeness for existence

For a prototype-admitted request, if an obligation is false at any point in the finite domain, then a certificate containing that point, the correct obligation name, and the receiver-defined trace is accepted, subject to correct bindings and encoding. The checker evaluates the same point and obtains the same false root and trace.

## Proposition 3: no leastness theorem

A single accepted violating point does not establish that earlier points under the canonical `(obligation, trace, input)` ordering satisfy all obligations. A nonleast violating point is therefore valid existential evidence. Canonical minimality requires checking all preceding candidates or a stronger proof that excludes them.

## Proposition 4: full-vector/topological work equivalence

Under the artifact's cell-count convention, both the full-vector checker and the memoized topological direct evaluator perform one local operation for each `(node, point)` pair. Both therefore perform `|C| x |D|` semantic-cell operations. The retained certificate-rebuild diagnostic still receives the certificate: its 309,582 internal recursive visits are separate from its 45,198 outer proof-cell checks and from the certificate-free `Session/direct_result` timing path.

## Trusted assumptions

The arguments are conditional on correct receiver implementation, the stated finite semantics, and collision resistance of SHA-256. The artifact supplies exhaustive differential checks on its population, strict-boundary tests, and targeted mutation controls; these are evidence, not mechanical proof.


## Conservative selector admission

Mathematical totality and executable admission are distinct. The selector `(x == 0u) || ((1u / x) > 0u)` is defined at every point of the retained test domain `{0,1,2}` by short-circuit semantics, but the current simplifier does not reduce its definedness term directly to `true`. Producer, full checker, and compact checker all reject that request before certificate evaluation. This is a conservative incompleteness boundary, not an observed wrong acceptance.
