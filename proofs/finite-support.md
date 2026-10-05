# Finite support, complete coverage, and ordered diagnostics

## Scope and status

This is a hand proof about the mathematical construction defined below. It is not a proof-assistant development or a general proof of the Python implementations. The retained exhaustive tests check finitely many instantiations and the implementations' agreement with separate oracles. Neither those tests nor this argument establishes unrestricted C correctness, inferred repair intent, minimal supports, a compact proof system, or research novelty.

The concrete prototype has 32-bit unsigned values, no side effects within expressions, initialized scalar variables, braced conditionals, short-circuit Boolean expressions, and one final return. There are no loops, arrays, pointers, external calls, signed values, or I/O. A source-if trace is a sequence of source-level if-site decisions; internal short-circuit steps and native compiler branches are not trace events.

## 1. Authoritative request and outcomes

Let W = {0,...,2^32-1}. Fix an ordered list I = (x_1,...,x_n) and nonempty, finite, ordered subsets D_i of W. The domain is the CARTESIAN product D = product_i D_i. The request is (P,Q,T,R,D), with original P, candidate Q, reference T, and a Boolean selector R that is semantically defined at every point of D. The consumer, not the certificate, chooses this complete request and its coordinate order.

The mathematical semantics permits every such total selector. The concrete prototype is deliberately conservative: after parsing R, its reconstructed definedness term must simplify directly to the Boolean constant `true` under the current simplifier. This stronger prototype-admission condition is used by the executable completeness claims. The short-circuit selector `(x == 0u) || ((1u / x) > 0u)` is semantically defined on `{0,1,2}`, but the current simplifier does not establish direct `true`; the producer and both checkers therefore reject it before obligation construction.

For a program F and input u in D, let exec_F(u) = (d_F(u),v_F(u),tau_F(u)). Here d is a Boolean definedness flag, v is the returned unsigned value when d is true and has no semantic meaning otherwise, and tau is the source-if trace up to return or the first undefined operation. The mathematical interpreter stops at undefined division/remainder by zero or a shift by at least 32. This stopping convention supplies a diagnostic prefix; it does not assert that an ISO C implementation must execute such a prefix on an undefined execution.

The declared obligation predicates, in this fixed order, are:

    O_0(u) = d_Q(u)
    O_1(u) = not R(u) or (d_Q(u) and d_T(u) and v_Q(u)=v_T(u))
    O_2(u) = R(u) or (d_Q(u) and d_P(u) and v_Q(u)=v_P(u)).

Equality values are consulted only under the accompanying definedness conditions. Because the language is loop-free and every admitted function ends in a return, definedness also implies termination in this model. The preservation policy deliberately requires P to be defined on the unaffected partition. A request with P undefined there is not made satisfiable by interpreting undefined behavior as an arbitrary expected value.

## 2. Total symbolic terms and source translation

Use typed acyclic terms with constants, input variables, modular unsigned operations, Boolean operations, comparisons and if-then-else. Arithmetic division and remainder are totalized to zero at a zero divisor; shifts are totalized to zero at an out-of-range amount. These are INTERNAL term values, never values assigned to undefined C executions. Every source expression is translated to a pair (v_e,d_e).

For constants and initialized variable reads, d_e=true. Complement and Boolean negation retain their operand's flag. For an ordinary binary operation, d_e is the conjunction of operand flags; division/remainder also require a nonzero right value, and shifts require a right value below 32. The value component uses the corresponding total term operation. Arithmetic is reduced modulo 2^32 where specified; comparisons return Booleans and are not admitted as arithmetic operands in the prototype.

For short-circuit conjunction and disjunction:

    v_(a&&b) = v_a and v_b
    d_(a&&b) = d_a and ite(v_a,d_b,true)
    v_(a||b) = v_a or v_b
    d_(a||b) = d_a and ite(v_a,true,d_b).

A symbolic environment maps initialized scalar names to value terms. A block transformation returns an updated environment and a block-definedness term. An assignment stores the expression's value term and conjoins its definedness with the running flag, including assignments whose values are later unused or overwritten. Both branches of an if are translated from the same incoming environment. For guard (g,d_g), branch results (E_t,d_t) and (E_f,d_f), the outgoing value of every scalar a is ite(g,E_t[a],E_f[a]); block definedness contributes d_g and ite(g,d_t,d_f). It is conjoined with earlier statement definedness. The final return adds the return-expression flag.

To construct a trace, assign if sites in source preorder. Maintain an incoming path predicate p and a running block-alive predicate a. At an if, emit (site, reach, g), where reach=p and a and d_g. Translate the then branch with path reach and g, the else branch with path reach and not g. After the if, update a using the guard and selected branch's definedness. Evaluate the emitted events in their construction order and retain exactly those with true reach; their Boolean guard values give tau.

### Lemma 1 (expression and block correspondence)

For a well-typed expression evaluated in a concrete initialized store represented by the symbolic environment, d_e is true exactly when the expression is defined. If true, v_e equals its concrete value. For an admitted block started in such a store, the translated block flag is true exactly when the block completes without undefined behavior; when true, every outgoing scalar term agrees with the concrete store. The analogous statement holds for the final return and whole function.

**Proof.** Induct on expression structure. Constants and variable reads are immediate. For a unary expression, apply the induction hypothesis to the operand and then the specified total operation. For a strict binary expression, an undefined operand makes the conjunction false. If both operands are defined, the additional divisor/shift precondition is exactly the domain of the concrete operation. On that domain, totalization agrees with the concrete operation. For conjunction, first consider an undefined left operand: both concrete expression and flag are undefined/false. For a defined false left operand, the right expression is not executed and the flag is true irrespective of d_b. For a defined true left operand, the induction hypothesis for b supplies exactly the value and definedness. Disjunction has the symmetric three cases. This covers the complete expression grammar.

Induct on block structure and sequential position. An initialized assignment is covered by the expression induction; on success the updated environment equals the updated store. On failure, the running flag is false, irrespective of any subsequently constructed symbolic values. If an earlier statement has already failed, conjoining further flags cannot make the block defined. At an if with a defined guard, exactly one branch executes; the induction hypothesis for that branch gives its completion flag and outgoing environment, and each ite selects that environment. An undefined guard makes the flag false before either branch is executed. Sequential composition applies these cases in order. The final return is an expression in the resulting environment. There is no early return or loop case in the language. QED.

### Lemma 2 (trace correspondence)

The filtered symbolic event list equals the concrete source-if trace, including traces that end at undefined operations.

**Proof.** Induct on the structured block traversal. For an event to be appended concretely, its containing path must have been selected, all prior statements on that path must have completed, and its guard must be defined. By Lemma 1 these are exactly p, a and d_g, so their conjunction is precisely reach. When reach is true, the guard value agrees by Lemma 1. A failure before the event makes reach false; a failure in a guard excludes that guard's decision itself. Recursive branch traversal places all possible then events before all possible else events, but at most one branch's events can be retained. Thus filtering the construction order yields exactly the selected execution order. Joining the block with its following statements carries forward the selected branch's completion flag, suppressing later events after a failure. A final-return failure occurs after all if events and does not change the accumulated trace. QED.

### Lemma 3 (simplification and free-variable support)

The following simplifications preserve the denotation of total typed terms: Boolean constants, idempotence and absorbing/identity laws for conjunction/disjunction; conditional selection by a constant; equal-branch conditional elimination; double negation; reflexive comparisons of an identical unsigned term; and evaluation of a constant-only term under the totalized operations. A term's set of free input variables is a support of its denotation.

**Proof.** The Boolean laws follow from the two-element truth tables. For ite, a constant guard selects its specified branch, and equal branches give the same value for either guard. An unsigned value compares equal to itself, so equality and weak inequalities are true and inequality and strict inequalities are false. Constant evaluation uses exactly the declared operation, including its totalization at invalid operands. These statements concern total terms only: they do not authorize removal of an accompanying source-definedness flag. Finally induct on an acyclic term. Constants have no dependencies, an input depends only on itself, and each compound term is a deterministic function of its children. Inputs agreeing on the union of their free variables give equal child denotations and therefore equal compound denotations. QED.

The prototype uses these simplifications and hash-consing. Its internal DAG is an expression-sharing representation, not a transmitted proof DAG. Hash-consing is not a proof of global minimality or bit-vector equivalence.

## 3. Semantic and trace supports

A set S subseteq I is a support of f:D->A if u restricted to S = v restricted to S implies f(u)=f(v). A superset of a support is again a support. By Lemmas 1 and 3, free variables of each compiled obligation O_j form a semantic support B_j. They include dependencies introduced by definedness, not only returned values. These supports need not be least, and producer and receiver need not compute identical conservative sets.

By Lemmas 2 and 3, the union of free variables of every reach predicate and guard value is a trace support T_Q. The independently implemented receiver uses another, possibly larger trace support: it unions the variables of each symbolic if-guard value, each if-guard definedness predicate, and the definedness predicate of each assignment/declaration. Those terms use the symbolically propagated environments. A final-return flag need not be added solely for tracing.

### Lemma 4 (receiver trace-support soundness)

The receiver's stated union is a support of tau_Q.

**Proof.** Consider two inputs agreeing on that union. By Lemma 3, every collected guard value and every collected pre-return statement/guard-definedness term has the same value on both inputs. Induct along their common execution prefix. Initially both are at function entry. If the next statement is an assignment, Lemma 1 makes its completion decision equal for both; if it fails, both traces stop. Otherwise neither adds a trace event and both proceed. If the next statement is an if, its guard-definedness and, when defined, its Boolean value agree; therefore both stop before the event, or append the same event and choose the same branch. This inductive alignment justifies using the symbolic environment appropriate to the same reached path; no equality of all concrete stores is assumed. Every reached source statement is covered, including an assignment in a branch. At the final return, neither outcome adds another if event. Both traces are therefore equal. QED.

## 4. Coverage and replay protocol

For S subseteq I, write D_S for its projection product. When S is empty, D_S consists of one empty tuple, not zero tuples. Let lift_S(s) retain s on S and place the minimum of D_i in every discarded coordinate. Cartesianity guarantees lift_S(s) belongs to D. It is the lexicographically least member of its projection fiber.

For each obligation in fixed order, a certificate contains a listed support S_j and a map M_j:D_(S_j)->{false,true}, serialized as rows. The receiver independently derives B_j from its authoritative request. Schema validation requires B_j subseteq S_j subseteq I, ordered unique support names, valid-domain integer row keys (not JSON Booleans), Boolean assertions, no duplicate keys, and all three obligation identities in order. A complete table has exactly one row per element of D_(S_j).

After all schemas pass, the receiver checks complete coverage for all obligations. If a table has a hole it returns UNCOVERED before semantic row validation; this outcome does not attest that the remaining row assertions are correct. If coverage is complete it computes O_j(lift_(S_j)(s)) independently for every row and compares it with the assertion. A mismatch is INVALID, not an accepted semantic claim. If all assertions are faithful, all-true rows give ACCEPT; any false row gives REFUTED with a recomputed diagnostic. Unsupported syntax or configured admission bounds yield UNKNOWN. Input/certificate schema failures yield INVALID. No source supplied inside a certificate is executed or treated as authoritative.

### Theorem 1 (generator-independent soundness)

Assume the receiver correctly implements the mathematical interpreter, support construction, schema/coverage checks and row replay described here. If it returns ACCEPT, every O_j holds on every u in D, independently of how Q or its certificate was produced.

**Proof.** Fix j and u. Complete coverage provides the unique row s=u restricted to S_j. Acceptance implies its independently replayed truth is true. Since B_j subseteq S_j, Lemma 3 and the superset property give O_j(u)=O_j(lift_(S_j)(s))=true. This holds for each of the three obligation identities because their completeness and order were checked independently of the producer. The premises mention only the authoritative request and receiver checks, not the producer's method or rationale. QED.

### Corollary 1 (refutation soundness and conditional finite completeness)

A REFUTED outcome supplies an actual false declared obligation in D. If all obligations hold, a complete all-input certificate is accepted whenever source/term admission succeeds, its 3|D| rows fit the certificate bound, and replay fits the resource limit.

**Proof.** A faithful false row was independently evaluated at an input in D; the recomputed diagnostic ranges only over D and checks the same predicate. For completeness, take S_j=I for each j, enumerate each finite D exactly once, and attach the true independently computed assertion. All supports and coverage constraints then hold, so Theorem 1's checks succeed within the stated capacity premises. This is an existence claim, not a guarantee that the optimizing producer selects an accepted support, nor that 3|D| fits the prototype's 2,048-row cap for every admitted domain. QED.

## 5. Least diagnostics require their own observation support

Order source-if events by the pair (site,bit), where site is the preorder identifier and false=0 precedes true=1. Order finite traces lexicographically with a strict prefix before an extension. Input tuples follow the request's variable order and unsigned numeric order. Order violation witnesses first by obligation index, then trace, then full input. No cross-program or compiler-path invariance is claimed for this declared order.

### Theorem 2 (least violating diagnostic)

Let j be the first obligation false somewhere. Let H_j contain B_j union T_Q. Enumerate D_(H_j), lift each tuple, retain those for which O_j is false, and minimize (tau_Q(u),u). The result is the least violation of O_j over the entire D and, with the first-j rule, the least declared violation globally.

**Proof.** Each H_j fiber has constant obligation truth and constant trace by the two support properties. If a fiber violates the obligation, its minimum input is lift_(H_j)(s), because every discarded coordinate can independently take its domain minimum. With the trace fixed, that representative minimizes the witness key within the fiber. Every nonempty violating fiber is enumerated exactly once. A minimum over these fiber minima equals the minimum over their disjoint union. Choosing the first failing j accounts for the outermost witness-order component. Finiteness and a false obligation ensure the retained set is finite and nonempty. QED.

### Corollary 2 (least uncovered diagnostic)

Let A_j be the set of missing row keys of the first incomplete table. For hole predicate h_j(u)=[u restricted to S_j belongs to A_j], replace H_j by S_j union T_Q and minimize over inputs satisfying h_j. The returned input/trace is the least coverage hole, not necessarily a semantic counterexample.

**Proof.** Membership in A_j depends only on S_j. Apply the same fiber-minimum argument to h_j and tau_Q. There is no premise relating h_j to falsehood of O_j. Indeed, deleting a row from a valid certificate makes h_j true somewhere while all O_j can remain true. QED.

### Counterexample A (value-only support)

In a candidate that begins with `unsigned unused = 1u / (t ^ 3u);` and otherwise returns the reference result, the returned totalized value can be independent of t. All fixtures include t in {0,1,3}. A value-only projection lifts t to 0, where the unused expression is defined; it therefore misses the violation at t=3. The separate d_Q term prevents this elimination. This is a self-contained semantic example; undefined behavior is not executed as a native test.

### Counterexample B (semantic-only diagnostic support)

For fixture-01-overfit, D={0,1,3}^4, R is x=0, and the candidate first branches on z=0 only to update an unused, defined scratch value. It then computes y+x and adds one exactly when x=0 and y=3. Repair violations depend only on x,y. A semantic-only representative is (0,3,0,0) with trace [(0,1),(1,1)]. However (0,3,1,0) has trace [(0,0),(1,1)], which is smaller under the declared trace-first order. Adding trace support finds this true minimum. The exact request and oracle are retained in inputs/fixture-01-overfit.json and results/oracle/fixture-01-overfit.json.

### Boundary counterexample (non-Cartesian domains)

If a domain were instead {(0,1),(1,0)}, coordinate minima could produce (0,0), which is not an admitted input. The lifting and fiber-minimum proofs above would then fail. The prototype admits only Cartesian domains; a constrained-domain extension would need a valid minimum in each feasible fiber, not independent coordinate minima.

## 6. What the replay certificate does not buy

### Proposition 1 (zero-certificate feasibility without a work restriction)

For an explicitly finite D and a terminating interpreter for the declared fragment, no positive lower bound on necessary transmitted evidence follows merely from generator independence and sound/complete checking.

**Proof.** A receiver can ignore any evidence, enumerate all of D and the three predicates, and return their exact classification. It transmits zero certificate symbols and trusts no generator. The computation may be expensive, but without a restriction on receiver work that is not excluded. Thus necessity of positive evidence would need an additional formal constraint. QED.

### Proposition 2 (direct support replay dominates table replay in semantic row count)

Fix one admitted request. Compare (a) the above receiver supplied with a complete, schema-valid, replay-consistent table having supports S_j, and (b) a fresh receiver that receives NO certificate and enumerates its own supports B_j, evaluates every predicate cell without asymmetric early stopping, and computes the same canonical diagnostic. Both return the same ACCEPT/REFUTED classification and the same violation witness. Arm (b) uses no more obligation replay rows: sum_j |D_(B_j)| <= sum_j |D_(S_j)|.

**Proof.** B_j subseteq S_j, and every domain has at least one element, so the product inequality holds term by term. The support property makes either complete enumeration equivalent to quantifying O_j over D. Both canonical searches use the receiver's same B_j union T_Q and same ordering; therefore their witnesses agree. The proposition is intentionally not about malformed or incomplete certificates, for which table-validation outcomes have no direct semantic counterpart. QED.

For deterministic role/input execution with initially empty per-arm caches and the same predicate evaluation order within a row, the direct validation arm's full-input representatives are also a subset of the table arm's: extend every B_j key to an S_j key using domain minima. Every required role/input source execution at that representative is therefore requested by the table arm as well, unless already cached there. Canonical search adds the same set of predicate/trace requests to both arms. Thus direct replay needs no more source interpretation under this specific caching model. This is not a theorem about arbitrary verifiers, proof-carrying code, solver proofs, asymptotic running time, or memory usage. Parser costs, table allocation, host-language operations and different implementations require separate accounting.

The measured fresh-receiver null control checks this proposition on all 80 retained requests. Both arms use 2,522 semantic replay rows and 79,877 source-interpreter steps; the certificate arm additionally processes 2,522 certificate rows and 2,522 coverage cells. This is evidence against a computational-enablement claim for THIS format. It is not a new impossibility result for semantic certificates in general.

## 7. Relation to the executable evidence

The source/term correspondence arguments are supplied mathematical proofs of definitions, not a formal verification of a parser. The producer uses a regex scanner and Pratt parser; the receiver uses a separate scanner, shunting-yard parser, dependency algebra and concrete interpreter. Neither imports the other. The separately implemented full-domain oracle imports neither and parses no source. Native C checks compare only defined return values, not model traces or undefined outcomes. Shared design authorship and shared mathematical assumptions remain sources of correlated error.

The result files distinguish measured finite checks from these general mathematical arguments. `results/study.json`, `results/cases.json`, the per-case oracles/certificates, `results/regression.json`, and `results/null-control.json` retain the claims and controls. Exact replay procedures are in README.md. The study is synthetic: it establishes no public Codeflaws result, model-repair success rate, user benefit or general implementation proof.
