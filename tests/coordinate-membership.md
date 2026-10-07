# Portable coordinate-membership conformance

From this standalone artifact root, with Python 3.10+ and no third-party packages:

```sh
python -B tests/test_coordinate_membership.py
```

The command can also be invoked by absolute script path from any working directory.
All assets are located relative to the script. It prints a bounded JSON test
summary and exits zero on success. It does not run the complete reproduction,
grammar, native or security campaign.

`product_membership_reference.py` is a test-only reference: it independently
repeats request admission, enumerates the finite Cartesian product, and uses
list membership. Its point semantics shares the current full checker's parser,
circuit reconstruction and local-value rules. This is membership-algorithm
independence, not independent whole-language semantics. Production imports
neither test file.

The regression checks nine valid domain layouts; 40 malformed authoritative
requests and error precedence; exact input order and point types; 8,644 finite
membership identities; bounded complete compact checks for in/out-of-domain
points; packet bindings, exact traces and conservative definedness; all 285
retained compact packets against both membership algorithms; and all 380
retained full certificates against their manifests and the current strong
topological path. Six benign full-certificate controls retain rejection checks.
The product-call control requires enumeration in the reference and full-vector
validator but none in the current compact receiver.

Removing product allocation does not remove semantic work. Compact checking
still evaluates N circuit nodes and reports N `refutation_cells`; full proof
checking still validates NM `proof_cells`, and the direct path retains its
NM `topological_cells`.

## Optional paired benchmark description — no automatic timing

This regression performs no timing. A separately authorized benchmark can use
`load_pair`, `retained_pair`, `synthetic_request` and `packet_for` from the
local regression to compare the product-enumerating reference with the current
compact receiver, without needing an old source tree.

Fix the workload before measurement: eight retained fixture families
1, 2, 7, 8, 16, 17, 18, 19, each with overfit/regression/undefined packets
(24 retained cases); and two-coordinate synthetic domains with Cartesian
sizes 1, 9, 81 and 4096, three obligation classes, and first/last admitted
points (24 mechanism cases; the two size-one positions coincide by design).
Preflight exact results, diagnostics and N-cell counts on identical decoded
requests/packets.

Use three warm-up calls per arm/case, 20 paired repetitions and batch five,
counterbalancing reference/current order by repetition plus case index.
Time only the complete compact check: include admission, packet/source binding,
hashes, parsing, point evaluation and trace checking; exclude imports, asset
loading, JSON decoding and assertions. Compare outputs and immutability outside
the measured interval. Retain raw paired samples and medians of paired ratios,
report retained and synthetic populations separately, and record host/runtime.
Apply a small explicit time ceiling and do not turn an aborted run into success.

This is a membership-mechanism comparison. Run timing alone, retain all samples,
and do not infer campaign-wide acceleration or reduced semantic work from a
small pooled ratio. No timing driver is invoked by this regression.
