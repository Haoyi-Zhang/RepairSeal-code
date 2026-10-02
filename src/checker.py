"""Independent receiver for finite-support replay certificates.

This file imports only the Python standard library. It does NOT import the
producer, the fixture oracle, or any proof-search routine. A separate scanner,
shunting-yard parser, symbolic dependency analysis and concrete C interpreter
implement the receiver's trusted computation. This implementation is tested,
not mechanically verified.
"""
from __future__ import annotations
import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

UINT_MAX = 4294967295
OBLIGATIONS = ("defined", "repair", "preserve")
LEVEL = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5, "==": 6, "!=": 6,
         "<": 7, ">": 7, "<=": 7, ">=": 7, "<<": 8, ">>": 8,
         "+": 9, "-": 9, "*": 10, "/": 10, "%": 10, "u!": 11, "u~": 11}
COMPARE = {"<", ">", "<=", ">=", "==", "!="}
C_KEYWORDS = frozenset("auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local".split())

class Unsupported(ValueError):
    pass

class Invalid(ValueError):
    pass

class Undefined(Exception):
    pass

def no_count(kind: str, n: int = 1) -> None:
    pass

def identifier(s: str) -> bool:
    return type(s) is str and bool(s) and s not in C_KEYWORDS and not s.startswith("__") and not (s.startswith("_") and len(s) > 1 and s[1].isupper()) and (s[0] == "_" or "a" <= s[0] <= "z" or "A" <= s[0] <= "Z") and all(
        c == "_" or "a" <= c <= "z" or "A" <= c <= "Z" or "0" <= c <= "9" for c in s)

def scan(text: str) -> list[str]:
    if type(text) is not str or len(text) > 16384 or len(text.splitlines()) > 250:
        raise Unsupported("source-size bound")
    if "\\" in text or "??" in text or any(c not in " \t\r\n\v\f" and not 32 <= ord(c) <= 126 for c in text):
        raise Unsupported("preprocessing and non-ASCII source excluded")
    out = []; i = 0
    while i < len(text):
        c = text[i]
        if c in " \t\r\n\v\f": i += 1; continue
        if text.startswith("//", i):
            j = text.find("\n", i + 2); i = len(text) if j < 0 else j + 1; continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0: raise Unsupported("unterminated comment")
            i = j + 2; continue
        if c == "_" or "a" <= c <= "z" or "A" <= c <= "Z":
            j = i + 1
            while j < len(text) and (text[j] == "_" or text[j].isascii() and text[j].isalnum()): j += 1
            out.append(text[i:j]); i = j
        elif "0" <= c <= "9":
            j = i + 1
            while j < len(text) and "0" <= text[j] <= "9": j += 1
            if j == len(text) or text[j] != "u": raise Unsupported("only unsigned decimal literals")
            token = text[i:j + 1]
            if len(token) > 11 or int(token[:-1]) > UINT_MAX: raise Unsupported("literal bound")
            if len(token) > 2 and token[0] == "0": raise Unsupported("no octal literals")
            out.append(token); i = j + 1
        elif text[i:i + 2] in {"==", "!=", "<=", ">=", "<<", ">>", "&&", "||"}:
            out.append(text[i:i + 2]); i += 2
        elif c in "{}(),;=+-*/%&|^<>!~":
            out.append(c); i += 1
        else:
            raise Unsupported("token outside fragment")
        if len(out) > 4096: raise Unsupported("token budget")
    return out

class Source:
    """Scanner + shunting-yard expression parser, deliberately separate from producer."""
    def __init__(self, text: str):
        self.tokens = scan(text); self.at = 0; self.site = 0

    def current(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def eat(self, token=None):
        got = self.current()
        if got is None or token is not None and got != token:
            raise Unsupported("grammar mismatch")
        self.at += 1; return got

    def name(self):
        n = self.eat()
        if not identifier(n) or n in {"unsigned", "if", "else", "return"}:
            raise Unsupported("invalid name")
        return n

    def expression(self, stops: set[str]):
        stack = []; output = []; want_operand = True; parentheses = 0
        def reduce_operator():
            op = stack.pop()
            if op in {"u!", "u~"}:
                if not output: raise Unsupported("missing unary operand")
                output.append((op[1:], output.pop()))
            else:
                if len(output) < 2: raise Unsupported("missing binary operand")
                right = output.pop(); left = output.pop(); output.append((op, left, right))
        while self.current() is not None:
            token = self.current()
            if token in stops and parentheses == 0: break
            self.eat()
            if token == "(":
                if not want_operand: raise Unsupported("calls excluded")
                parentheses += 1
                if parentheses > 64: raise Unsupported("expression nesting bound")
                stack.append(token)
            elif token == ")":
                if parentheses == 0 or want_operand: raise Unsupported("parenthesis")
                while stack and stack[-1] != "(": reduce_operator()
                if not stack: raise Unsupported("parenthesis")
                stack.pop(); parentheses -= 1
            elif token in {"!", "~"} and want_operand:
                stack.append("u" + token)
            elif token in LEVEL and not want_operand:
                while stack and stack[-1] != "(" and LEVEL[stack[-1]] >= LEVEL[token]: reduce_operator()
                stack.append(token); want_operand = True
            elif want_operand and token.endswith("u") and token[:-1].isascii() and token[:-1].isdigit():
                output.append(("N", int(token[:-1]))); want_operand = False
            elif want_operand and identifier(token) and token not in {"unsigned", "if", "else", "return"}:
                output.append(("V", token)); want_operand = False
            else:
                raise Unsupported("expression token sequence")
        if parentheses or want_operand: raise Unsupported("incomplete expression")
        while stack: reduce_operator()
        if len(output) != 1: raise Unsupported("expression arity")
        # Bound semantic recursion separately from token/parenthesis counts.
        todo = [(output[0], 1)]; visited = 0
        while todo:
            e, depth = todo.pop(); visited += 1
            if depth > 64 or visited > 2048: raise Unsupported("expression tree bound")
            if e[0] not in {"N", "V"}: todo.extend((a, depth + 1) for a in e[1:])
        return output[0]

    def statements(self, level=0):
        if level > 64: raise Unsupported("control nesting bound")
        self.eat("{"); sequence = []
        while self.current() != "}":
            token = self.current()
            if token == "unsigned":
                if level: raise Unsupported("declarations only in outer block")
                self.eat(); name = self.name(); self.eat("=")
                e = self.expression({";"}); self.eat(";"); sequence.append(("D", name, e))
            elif token == "if":
                self.eat(); site = self.site; self.site += 1
                if self.site > 128: raise Unsupported("control-block bound")
                self.eat("("); condition = self.expression({")"}); self.eat(")")
                positive = self.statements(level + 1); self.eat("else"); negative = self.statements(level + 1)
                sequence.append(("I", site, condition, positive, negative))
            elif token == "return":
                if level: raise Unsupported("early returns excluded")
                self.eat(); e = self.expression({";"}); self.eat(";"); sequence.append(("R", e))
                if self.current() != "}": raise Unsupported("return placement")
            else:
                n = self.name(); self.eat("="); e = self.expression({";"}); self.eat(";")
                sequence.append(("A", n, e))
        self.eat("}"); return sequence

    def function(self):
        self.eat("unsigned"); self.eat("f"); self.eat("(")
        args = []
        if self.current() != ")":
            while True:
                self.eat("unsigned"); args.append(self.name())
                if self.current() != ",": break
                self.eat(",")
        self.eat(")")
        if len(set(args)) != len(args) or not 1 <= len(args) <= 8: raise Unsupported("parameter count")
        code = self.statements()
        if self.current() is not None or not code or code[-1][0] != "R":
            raise Unsupported("whole-function boundary")
        return args, code

@dataclass(eq=False)
class Symbol:
    tag: str
    data: object
    children: tuple
    variables: frozenset

class Algebra:
    """Receiver-side abstract expression algebra; never executes producer terms."""
    def __init__(self, tick: Callable):
        self.pool = {}; self.tick = tick
        self.T = self.constant(True); self.F = self.constant(False)

    def make(self, tag, data=None, children=()):
        key = (tag, data, children)
        if key not in self.pool:
            if len(self.pool) >= 2048: raise Unsupported("symbolic dependency bound")
            variables = frozenset({data}) if tag == "input" else frozenset().union(*(c.variables for c in children))
            self.pool[key] = Symbol(tag, data, children, variables); self.tick("checker_symbolic_nodes")
        return self.pool[key]

    def constant(self, v):
        return self.make("boolean" if type(v) is bool else "unsigned", v)

    def combine(self, op, *cs):
        if op == "conj":
            if cs[0] is self.F or cs[1] is self.F: return self.F
            if cs[0] is self.T: return cs[1]
            if cs[1] is self.T or cs[0] is cs[1]: return cs[0]
        if op == "disj":
            if cs[0] is self.T or cs[1] is self.T: return self.T
            if cs[0] is self.F: return cs[1]
            if cs[1] is self.F or cs[0] is cs[1]: return cs[0]
        if op == "choose":
            if cs[0] is self.T: return cs[1]
            if cs[0] is self.F: return cs[2]
            if cs[1] is cs[2]: return cs[1]
        if op == "negate":
            if cs[0] is self.T: return self.F
            if cs[0] is self.F: return self.T
            if cs[0].tag == "negate": return cs[0].children[0]
        if op in COMPARE and cs[0] is cs[1]:
            return self.constant(op in {"==", "<=", ">="})
        if all(c.tag in {"boolean", "unsigned"} for c in cs):
            a = [c.data for c in cs]
            if op == "conj": v = a[0] and a[1]
            elif op == "disj": v = a[0] or a[1]
            elif op == "choose": v = a[1] if a[0] else a[2]
            elif op == "negate": v = not a[0]
            elif op == "invert": v = UINT_MAX ^ a[0]
            elif op == "+": v = (a[0] + a[1]) % (UINT_MAX + 1)
            elif op == "-": v = (a[0] - a[1]) % (UINT_MAX + 1)
            elif op == "*": v = a[0] * a[1] % (UINT_MAX + 1)
            elif op == "/": v = 0 if a[1] == 0 else a[0] // a[1]
            elif op == "%": v = 0 if a[1] == 0 else a[0] % a[1]
            elif op == "<<": v = 0 if a[1] >= 32 else (a[0] * (2 ** a[1])) % (UINT_MAX + 1)
            elif op == ">>": v = 0 if a[1] >= 32 else a[0] // (2 ** a[1])
            elif op == "&": v = a[0] & a[1]
            elif op == "|": v = a[0] | a[1]
            elif op == "^": v = a[0] ^ a[1]
            elif op == "==": v = a[0] == a[1]
            elif op == "!=": v = a[0] != a[1]
            elif op == "<": v = a[0] < a[1]
            elif op == ">": v = a[0] > a[1]
            elif op == "<=": v = a[0] <= a[1]
            elif op == ">=": v = a[0] >= a[1]
            else: raise Unsupported("dependency operator")
            return self.constant(v)
        return self.make(op, children=tuple(cs))

class DependencyAnalysis:
    def __init__(self, algebra: Algebra, parameters):
        self.a = algebra; self.parameters = parameters; self.trace_variables = set()

    def expression(self, node, variables):
        a = self.a; token = node[0]
        if token == "N": return a.constant(node[1]), a.T, "number"
        if token == "V":
            if node[1] not in variables: raise Unsupported("undeclared/uninitialized read")
            return variables[node[1]], a.T, "number"
        if token in {"!", "~"}:
            v, safe, typ = self.expression(node[1], variables)
            if typ != ("truth" if token == "!" else "number"): raise Unsupported("unary type")
            return a.combine("negate" if token == "!" else "invert", v), safe, typ
        lhs, ld, lt = self.expression(node[1], variables)
        rhs, rd, rt = self.expression(node[2], variables)
        if token in {"&&", "||"}:
            if lt != "truth" or rt != "truth": raise Unsupported("Boolean grammar")
            tail = a.combine("choose", lhs, rd, a.T) if token == "&&" else a.combine("choose", lhs, a.T, rd)
            return a.combine("conj" if token == "&&" else "disj", lhs, rhs), a.combine("conj", ld, tail), "truth"
        if lt != "number" or rt != "number": raise Unsupported("numeric grammar")
        safe = a.combine("conj", ld, rd)
        if token in {"/", "%"}: safe = a.combine("conj", safe, a.combine("!=", rhs, a.constant(0)))
        if token in {"<<", ">>"}: safe = a.combine("conj", safe, a.combine("<", rhs, a.constant(32)))
        return a.combine(token, lhs, rhs), safe, "truth" if token in COMPARE else "number"

    def sequence(self, code, incoming):
        a = self.a; state = dict(incoming); safe = a.T
        for statement in code:
            kind = statement[0]
            if kind in {"D", "A"}:
                _, name, expression = statement
                if kind == "D" and name in state or kind == "A" and name not in state:
                    raise Unsupported("declaration discipline")
                if kind == "D" and len(state) >= 72: raise Unsupported("local variable bound")
                val, ok, typ = self.expression(expression, state)
                if typ != "number": raise Unsupported("assignment value type")
                self.trace_variables.update(ok.variables)
                state[name] = val; safe = a.combine("conj", safe, ok)
            elif kind == "I":
                _, _, guard, yes, no = statement
                choice, ok, typ = self.expression(guard, state)
                if typ != "truth": raise Unsupported("if guard type")
                self.trace_variables.update(choice.variables); self.trace_variables.update(ok.variables)
                st, dt = self.sequence(yes, state); sf, df = self.sequence(no, state)
                if set(st) != set(sf): raise Unsupported("branch variable scope")
                state = {v: a.combine("choose", choice, st[v], sf[v]) for v in st}
                safe = a.combine("conj", safe, a.combine("conj", ok, a.combine("choose", choice, dt, df)))
            else: raise Unsupported("statement boundary")
        return state, safe

    def analyze(self, code):
        env, ok = self.sequence(code[:-1], {p: self.a.make("input", p) for p in self.parameters})
        val, last, typ = self.expression(code[-1][1], env)
        if typ != "number": raise Unsupported("return type")
        return val, self.a.combine("conj", ok, last)


def evaluate(node, store, count):
    count("checker_steps")
    op = node[0]
    if op == "N": return node[1]
    if op == "V": return store[node[1]]
    if op == "!": return not evaluate(node[1], store, count)
    if op == "~": return UINT_MAX ^ evaluate(node[1], store, count)
    left = evaluate(node[1], store, count)
    if op == "&&": return bool(left and evaluate(node[2], store, count))
    if op == "||": return bool(left or evaluate(node[2], store, count))
    right = evaluate(node[2], store, count)
    if op == "+": return (left + right) & UINT_MAX
    if op == "-": return (left - right) & UINT_MAX
    if op == "*": return (left * right) & UINT_MAX
    if op in {"/", "%"}:
        if right == 0: raise Undefined()
        return left // right if op == "/" else left % right
    if op in {"<<", ">>"}:
        if right >= 32: raise Undefined()
        return ((left << right) & UINT_MAX) if op == "<<" else left >> right
    if op == "&": return left & right
    if op == "|": return left | right
    if op == "^": return left ^ right
    if op == "==": return left == right
    if op == "!=": return left != right
    if op == "<": return left < right
    if op == "<=": return left <= right
    if op == ">": return left > right
    if op == ">=": return left >= right
    raise Unsupported("concrete operator")


def execute(code, values, count):
    memory = dict(values); decisions = []
    def statements(seq):
        for st in seq:
            count("checker_steps")
            if st[0] in {"D", "A"}: memory[st[1]] = evaluate(st[2], memory, count)
            elif st[0] == "I":
                decision = bool(evaluate(st[2], memory, count))
                decisions.append((st[1], int(decision)))
                statements(st[3] if decision else st[4])
            else: raise Unsupported("concrete statement")
    try:
        statements(code[:-1]); value = evaluate(code[-1][1], memory, count)
        return True, value, tuple(decisions)
    except Undefined:
        return False, None, tuple(decisions)

class Session:
    def __init__(self, request: dict, count: Callable = no_count):
        required = {"id", "word_bits", "inputs", "original", "candidate", "reference", "repair_guard"}
        if type(request) is not dict or set(request) != required: raise Invalid("request schema")
        if type(request["id"]) is not str or len(request["id"]) > 64: raise Invalid("request identifier")
        if type(request["word_bits"]) is not int or request["word_bits"] != 32: raise Unsupported("word width")
        domains = request["inputs"]
        if type(domains) is not dict or not 1 <= len(domains) <= 8: raise Invalid("input schema")
        for name, domain in domains.items():
            if not identifier(name) or name in {"unsigned", "if", "else", "return"}: raise Invalid("input name")
            if type(domain) is not list or not 1 <= len(domain) <= 64: raise Invalid("domain size")
            if any(type(n) is not int or n < 0 or n > UINT_MAX for n in domain): raise Invalid("domain value")
            if sorted(set(domain)) != domain: raise Invalid("domain order/uniqueness")
        if math.prod(map(len, domains.values())) > 4096: raise Unsupported("input enumeration bound")
        self.request = request; self.names = list(domains); self.domains = domains; self.count = count
        self.cache = {}; self.code = {}; self.abstract = {}; a = Algebra(count)
        self.trace_variables = set()
        for role in ("original", "candidate", "reference"):
            parsed = Source(request[role]); count("checker_source_tokens", len(parsed.tokens))
            names, code = parsed.function()
            if names != self.names: raise Invalid("source parameter order")
            dep = DependencyAnalysis(a, names); self.abstract[role] = dep.analyze(code); self.code[role] = code
            if role == "candidate": self.trace_variables = dep.trace_variables
        source = Source(request["repair_guard"]); count("checker_source_tokens", len(source.tokens)); self.guard = source.expression(set())
        if source.current() is not None: raise Invalid("selector end")
        dep = DependencyAnalysis(a, self.names)
        guard, total, typ = dep.expression(self.guard, {n: a.make("input", n) for n in self.names})
        if typ != "truth" or total is not a.T: raise Unsupported("selector must be syntactically total")
        pv, pd = self.abstract["original"]; qv, qd = self.abstract["candidate"]; rv, rd = self.abstract["reference"]
        repair = a.combine("conj", qd, a.combine("conj", rd, a.combine("==", qv, rv)))
        preserve = a.combine("conj", qd, a.combine("conj", pd, a.combine("==", qv, pv)))
        roots = [qd, a.combine("disj", a.combine("negate", guard), repair), a.combine("disj", guard, preserve)]
        self.required = [r.variables for r in roots]
        self.symbols = len(a.pool)

    def run(self, role, values):
        key = (role, tuple(values[n] for n in self.names))
        if key not in self.cache:
            self.cache[key] = execute(self.code[role], values, self.count)
        return self.cache[key]

    def predicate(self, j, values):
        candidate = self.run("candidate", values)
        if j == 0: return candidate[0]
        selection = bool(evaluate(self.guard, values, self.count))
        if j == 1 and not selection or j == 2 and selection: return True
        other = self.run("reference" if j == 1 else "original", values)
        return candidate[0] and other[0] and candidate[1] == other[1]

    def cells(self, names):
        for cell in itertools.product(*(self.domains[n] for n in names)):
            self.count("checker_projected_points")
            full = {n: self.domains[n][0] for n in self.names}; full.update(zip(names, cell))
            yield cell, full

    def canonical(self, j, *, holes=None, table_support=None, full=False):
        deps = set(self.required[j] if holes is None else table_support)
        deps.update(self.trace_variables)
        support = self.names if full else [n for n in self.names if n in deps]
        least = None
        for _, values in self.cells(support):
            applies = not self.predicate(j, values) if holes is None else tuple(values[n] for n in table_support) in holes
            if not applies: continue
            trace = self.run("candidate", values)[2]; key = (trace, tuple(values[n] for n in self.names))
            self.count("counterexample_comparisons")
            if least is None or key < least: least = key
        if least is None: return None
        return {"obligation": OBLIGATIONS[j], "trace": [list(v) for v in least[0]], "input": list(least[1])}

    def check(self, certificate):
        if type(certificate) is not dict or set(certificate) != {"kind", "parts"} or certificate["kind"] != "finite-support-replay":
            raise Invalid("certificate header")
        parts = certificate["parts"]
        if type(parts) is not list or len(parts) != 3: raise Invalid("obligation list must be complete")
        prepared = []; total_rows = 0
        # Validate all schemas before interpreting any certificate assertion.
        for j, part in enumerate(parts):
            if type(part) is not dict or set(part) != {"obligation", "support", "rows"}: raise Invalid("part schema")
            if part["obligation"] != OBLIGATIONS[j]: raise Invalid("obligation identity/order")
            support = part["support"]
            if type(support) is not list or any(type(n) is not str for n in support): raise Invalid("support schema")
            if len(support) != len(set(support)) or any(n not in self.names for n in support): raise Invalid("support membership")
            if support != [n for n in self.names if n in support]: raise Invalid("support order")
            if not self.required[j] <= set(support): raise Invalid("insufficient semantic support")
            rows = part["rows"]
            if type(rows) is not list or len(rows) > 4096: raise Invalid("row bound")
            total_rows += len(rows)
            if total_rows > 2048: raise Invalid("certificate element bound")
            claims = {}
            for row in rows:
                self.count("certificate_steps")
                if type(row) is not dict or set(row) != {"key", "ok"} or type(row["ok"]) is not bool:
                    raise Invalid("row schema")
                key = row["key"]
                if type(key) is not list or len(key) != len(support): raise Invalid("key arity")
                if any(type(v) is not int or v not in self.domains[n] for n, v in zip(support, key)):
                    raise Invalid("key outside declared domain")
                key = tuple(key)
                if key in claims: raise Invalid("duplicate evidence cell")
                claims[key] = row["ok"]
            expected = set(itertools.product(*(self.domains[n] for n in support)))
            self.count("coverage_cells", len(expected))
            prepared.append((support, claims, expected - set(claims)))
        for j, (support, _, holes) in enumerate(prepared):
            if holes:
                return {"status": "UNCOVERED", "reason": "missing evidence, not a semantic refutation",
                        "witness": self.canonical(j, holes=holes, table_support=support), "checked_rows": 0,
                        "missing_cells": len(holes)}
        checked = 0; failing = []
        for j, (support, claims, _) in enumerate(prepared):
            for key, values in self.cells(support):
                actual = bool(self.predicate(j, values)); checked += 1
                if actual != claims[key]: raise Invalid("certificate assertion disagrees with independent replay")
                if not actual and j not in failing: failing.append(j)
        if failing:
            return {"status": "REFUTED", "reason": "a declared semantic obligation is false",
                    "witness": self.canonical(failing[0]), "checked_rows": checked}
        return {"status": "ACCEPT", "reason": "all declared cells covered and independently replayed",
                "witness": None, "checked_rows": checked}


def check(request, certificate, count: Callable = no_count):
    try:
        session = Session(request, count)
        answer = session.check(certificate)
        answer["symbolic_nodes"] = session.symbols
        return answer
    except Invalid as e:
        return {"status": "INVALID", "reason": str(e), "witness": None, "checked_rows": 0}
    except (Unsupported, RecursionError, MemoryError) as e:
        return {"status": "UNKNOWN", "reason": str(e), "witness": None, "checked_rows": 0}


def decode(text: str):
    if type(text) is not str or len(text.encode("utf-8")) > 2 * 1024 * 1024: raise Invalid("JSON byte bound")
    def object_pairs(pairs):
        d = {}
        for key, value in pairs:
            if key in d: raise Invalid("duplicate JSON member")
            d[key] = value
        return d
    def no_constant(_): raise Invalid("non-JSON numeric constant")
    try:
        return json.loads(text, object_pairs_hook=object_pairs, parse_constant=no_constant)
    except (json.JSONDecodeError, RecursionError, ValueError) as e:
        raise Invalid(str(e)) from e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    args = parser.parse_args()
    try:
        # The checker never executes submitted source, opens paths from a certificate,
        # or accepts a producer-supplied replacement for the consumer request.
        if args.request.stat().st_size > 2 * 1024 * 1024 or args.certificate.stat().st_size > 2 * 1024 * 1024:
            raise Invalid("file byte bound")
        answer = check(decode(args.request.read_text()), decode(args.certificate.read_text()))
    except (OSError, UnicodeError, Invalid) as e:
        answer = {"status": "INVALID", "reason": str(e), "witness": None, "checked_rows": 0}
    print(json.dumps(answer, sort_keys=True))
    return 0 if answer["status"] == "ACCEPT" else 2

if __name__ == "__main__":
    raise SystemExit(main())
