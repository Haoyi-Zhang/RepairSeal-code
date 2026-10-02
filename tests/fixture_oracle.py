"""Twenty hand-defined finite fixtures and an exact mathematical oracle.

The oracle imports neither implementation. It does not parse submitted source.
Each semantic function and its branch trace are written directly below. This is
an independently implemented finite oracle, not an independent human review.
"""
from __future__ import annotations
import itertools

M = 4294967295
NAMES = ("x", "y", "z", "t")
VARIANTS = ("correct", "overfit", "regression", "undefined")

# Each entry: name, reference body, differently structured candidate body,
# number of candidate-body if sites. Both bodies define unsigned r.
CORES = [
 ("modular addition", "unsigned r = x + y;", "unsigned r = y + x;", 0),
 ("modular subtraction", "unsigned r = x - y;", "unsigned r = x - y;", 0),
 ("modular multiplication", "unsigned r = x * (y + 1u);", "unsigned r = (y + 1u) * x;", 0),
 ("exclusive or", "unsigned r = x ^ y;", "unsigned r = y ^ x;", 0),
 ("bitwise and", "unsigned r = x & (y + 1u);", "unsigned r = (y + 1u) & x;", 0),
 ("bitwise or", "unsigned r = x | y;", "unsigned r = y | x;", 0),
 ("unsigned boundary addition", "unsigned r = x + 4294967295u;", "unsigned r = x - 1u;", 0),
 ("unsigned boundary multiplication", "unsigned r = x * 2147483649u;", "unsigned r = x + (x << 31u);", 0),
 ("nonzero division", "unsigned r = (x + 12u) / (y + 1u);", "unsigned r = (x + 12u) / (1u + y);", 0),
 ("nonzero remainder", "unsigned r = (x + 12u) % (y + 1u);", "unsigned r = (x + 12u) % (1u + y);", 0),
 ("bounded left shift", "unsigned r = x << y;", "unsigned r = x << y;", 0),
 ("bounded right shift", "unsigned r = x >> y;", "unsigned r = x >> y;", 0),
 ("minimum with different guards", "unsigned r = x;\nif (y < x) { r = y; } else { r = x; }", "unsigned r = x;\nif (x < y) { r = x; } else { r = y; }", 1),
 ("maximum with different guards", "unsigned r = x;\nif (y > x) { r = y; } else { r = x; }", "unsigned r = x;\nif (x > y) { r = x; } else { r = y; }", 1),
 ("unsigned absolute difference", "unsigned r = 0u;\nif (x >= y) { r = x - y; } else { r = y - x; }", "unsigned r = 0u;\nif (x >= y) { r = x - y; } else { r = y - x; }", 1),
 ("guarded division", "unsigned r = x;\nif (y == 0u) { r = x; } else { r = x / y; }", "unsigned r = x;\nif (y == 0u) { r = x; } else { r = x / y; }", 1),
 ("short-circuit guarded division", "unsigned r = x + 1u;\nif ((y != 0u) && (x / y > 0u)) { r = x / y; } else { r = x + 1u; }", "unsigned r = x + 1u;\nif ((y != 0u) && (x / y > 0u)) { r = x / y; } else { r = x + 1u; }", 1),
 ("nested branch dependence", "unsigned r = x;\nif (y == 0u) { if (z == 0u) { r = x + 1u; } else { r = x + 2u; } } else { r = x + y; }", "unsigned r = x;\nif (y == 0u) { if (z == 0u) { r = x + 1u; } else { r = x + 2u; } } else { r = x + y; }", 2),
 ("overwritten value", "unsigned r = x + z;", "unsigned r = x + y;\nr = x + z;", 0),
 ("value-relevant branch control", "unsigned r = x;\nif ((z & 1u) == 0u) { r = x ^ y; } else { r = x + y; }", "unsigned r = x;\nif ((z & 1u) == 0u) { r = x ^ y; } else { r = x + y; }", 1),
]


def domain(case: int) -> dict[str, list[int]]:
    x = [0, M - 1, M] if case in {7, 8} else [0, 1, 3]
    return {"x": x, "y": [0, 1, 3], "z": [0, 1, 3], "t": [0, 1, 3]}


def program(body: str) -> str:
    parameters = ", ".join("unsigned " + n for n in NAMES)
    return "unsigned f(" + parameters + ") {\n" + body + "\nreturn r;\n}\n"


def request(case: int, variant: str = "correct") -> dict:
    if not 1 <= case <= 20 or variant not in VARIANTS: raise ValueError("fixture identifier")
    _, reference, core, _ = CORES[case - 1]
    original = reference + "\nif (x == 0u) { r = r - 1u; } else { r = r; }"
    dead = "unsigned scratch = t;\nif (z == 0u) { scratch = scratch + 1u; } else { scratch = scratch + 2u; }\n"
    candidate = dead + core
    if variant == "overfit":
        candidate += "\nif ((x == 0u) && (y == 3u)) { r = r + 1u; } else { r = r; }"
    elif variant == "regression":
        last = domain(case)["x"][-1]
        candidate += f"\nif ((x == {last}u) && (y == 3u)) {{ r = r + 1u; }} else {{ r = r; }}"
    elif variant == "undefined":
        # Deliberately undefined only on t=3. No third-party source is executed.
        candidate = "unsigned unused = 1u / (t ^ 3u);\n" + candidate
    return {"id": f"fixture-{case:02d}-{variant}", "word_bits": 32, "inputs": domain(case),
            "original": program(original), "candidate": program(candidate), "reference": program(reference),
            "repair_guard": "x == 0u"}


def base_value(case: int, x: int, y: int, z: int) -> int:
    if case == 1: result = x + y
    elif case == 2: result = x - y
    elif case == 3: result = x * (y + 1)
    elif case == 4: result = x ^ y
    elif case == 5: result = x & (y + 1)
    elif case == 6: result = x | y
    elif case == 7: result = x - 1
    elif case == 8: result = x * 2147483649
    elif case == 9: result = ((x + 12) & M) // (y + 1)
    elif case == 10: result = ((x + 12) & M) % (y + 1)
    elif case == 11: result = x * (2 ** y)
    elif case == 12: result = x // (2 ** y)
    elif case == 13: result = min(x, y)
    elif case == 14: result = max(x, y)
    elif case == 15: result = abs(x - y)
    elif case == 16: result = x if y == 0 else x // y
    elif case == 17: result = x // y if y != 0 and x // y > 0 else x + 1
    elif case == 18: result = x + (1 if z == 0 else 2) if y == 0 else x + y
    elif case == 19: result = x + z
    elif case == 20: result = x ^ y if z % 2 == 0 else x + y
    else: raise ValueError("fixture index")
    return result & M


def observation(case: int, variant: str, point: tuple[int, ...]):
    x, y, z, t = point
    reference = base_value(case, x, y, z)
    original = (reference - 1) & M if x == 0 else reference
    if variant == "undefined" and t == 3:
        candidate = None; path = []
    else:
        path = [[0, int(z == 0)]]
        if case == 13: path.append([1, int(x < y)])
        elif case == 14: path.append([1, int(x > y)])
        elif case == 15: path.append([1, int(x >= y)])
        elif case == 16: path.append([1, int(y == 0)])
        elif case == 17: path.append([1, int(y != 0 and x // y > 0)])
        elif case == 18:
            path.append([1, int(y == 0)])
            if y == 0: path.append([2, int(z == 0)])
        elif case == 20: path.append([1, int(z % 2 == 0)])
        wrong = False
        if variant == "overfit": wrong = x == 0 and y == 3
        elif variant == "regression": wrong = x == domain(case)["x"][-1] and y == 3
        if variant in {"overfit", "regression"}:
            path.append([1 + CORES[case - 1][3], int(wrong)])
        candidate = (reference + int(wrong)) & M
    defined = candidate is not None
    truth = [defined, x != 0 or defined and candidate == reference,
             x == 0 or defined and candidate == original]
    return {"input": list(point), "original": original, "candidate": candidate,
            "reference": reference, "trace": path, "truth": [bool(v) for v in truth]}


def exhaustive(case: int, variant: str):
    return [observation(case, variant, p) for p in itertools.product(*domain(case).values())]


def least_violation(rows):
    for j, label in enumerate(("defined", "repair", "preserve")):
        bad = [r for r in rows if not r["truth"][j]]
        if bad:
            row = min(bad, key=lambda r: (r["trace"], r["input"]))
            return {"obligation": label, "trace": row["trace"], "input": row["input"]}
    return None


def least_hole(rows, support, missing, obligation=0):
    at = [NAMES.index(n) for n in support]
    hits = [r for r in rows if tuple(r["input"][k] for k in at) in missing]
    row = min(hits, key=lambda r: (r["trace"], r["input"]))
    return {"obligation": ("defined", "repair", "preserve")[obligation], "trace": row["trace"], "input": row["input"]}
