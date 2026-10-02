"""Untrusted producer: parse the small C fragment, build a term DAG, enumerate support cells.

No checker module is imported. All inputs are interpreted as data. The emitted
certificate is a finite replay table, not an SMT proof or a general-C certificate.
"""
from __future__ import annotations
import itertools
import re
from dataclasses import dataclass
from typing import Callable

MASK = (1 << 32) - 1
IDS = ("defined", "repair", "preserve")
ARITH = {"+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"}
REL = {"==", "!=", "<", "<=", ">", ">="}
RESERVED = set("auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local".split())
MAX_AST_DEPTH = 64
MAX_AST_NODES = 4096
MAX_LITERAL_DIGITS = 10
PREC = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
        "==": 6, "!=": 6, "<": 7, "<=": 7, ">": 7, ">=": 7,
        "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}

class ProducerError(ValueError):
    pass

def _noop(kind: str, count: int = 1) -> None:
    pass

def _validate_expression_tree(root) -> tuple[int, int]:
    stack = [(root, 1)]
    nodes = 0
    maximum = 0
    while stack:
        expr, depth = stack.pop()
        nodes += 1
        maximum = max(maximum, depth)
        if depth > MAX_AST_DEPTH:
            raise ProducerError("AST depth")
        if nodes > MAX_AST_NODES:
            raise ProducerError("AST node bound")
        op = expr[0]
        if op in {"num", "var"}:
            children = ()
        elif op in {"!", "~"}:
            children = (expr[1],)
        else:
            children = (expr[1], expr[2])
        stack.extend((child, depth + 1) for child in children)
    return nodes, maximum


def _validate_program_tree(statements) -> tuple[int, int]:
    total = 0
    maximum = 0
    stack = list(statements)
    while stack:
        statement = stack.pop()
        tag = statement[0]
        if tag in {"decl", "set"}:
            expressions = (statement[2],)
        elif tag == "ret":
            expressions = (statement[1],)
        elif tag == "if":
            expressions = (statement[2],)
            stack.extend(statement[3])
            stack.extend(statement[4])
        else:
            raise ProducerError("AST statement")
        for expression in expressions:
            count, depth = _validate_expression_tree(expression)
            total += count
            maximum = max(maximum, depth)
            if total > MAX_AST_NODES:
                raise ProducerError("AST node bound")
    return total, maximum

class Parser:
    def __init__(self, source: str):
        if not isinstance(source, str) or len(source) > 16384 or len(source.splitlines()) > 250:
            raise ProducerError("source bound")
        if "\\" in source or "??" in source or any(c not in " \t\r\n\v\f" and not 32 <= ord(c) <= 126 for c in source):
            raise ProducerError("no preprocessing or non-ASCII source")
        source = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
        pat = re.compile(r"[ \t\r\n\v\f]+|[A-Za-z_][A-Za-z_0-9]*|[0-9]+u|==|!=|<=|>=|<<|>>|&&|\|\||[{}(),;=+*/%&|^<>!~\-]")
        self.ts = []
        pos = 0
        while pos < len(source):
            m = pat.match(source, pos)
            if m is None:
                raise ProducerError("outside lexical fragment")
            t = m.group(0)
            if not t.isspace(): self.ts.append(t)
            pos = m.end()
        if len(self.ts) > 4096: raise ProducerError("token bound")
        self.i = 0
        self.branches = 0
        self.depth = 0

    def peek(self) -> str:
        return self.ts[self.i] if self.i < len(self.ts) else "<end>"

    def take(self, expected: str | None = None) -> str:
        t = self.peek()
        if t == "<end>" or (expected is not None and t != expected):
            raise ProducerError(f"expected {expected}, found {t}")
        self.i += 1
        return t

    def ident(self) -> str:
        t = self.take()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", t) or t in RESERVED or t.startswith("__") or (t.startswith("_") and len(t) > 1 and t[1].isupper()):
            raise ProducerError("identifier required")
        return t

    def expr(self, minimum: int = 1):
        self.depth += 1
        if self.depth > 64: raise ProducerError("expression depth")
        t = self.take()
        if t == "(":
            a = self.expr(); self.take(")")
        elif t in {"!", "~"}:
            a = (t, self.expr(11))
        elif re.fullmatch(r"[0-9]+u", t):
            digits = t[:-1]
            if len(digits) > MAX_LITERAL_DIGITS: raise ProducerError("literal length")
            if len(t) > 2 and t[0] == "0": raise ProducerError("no octal literals")
            n = int(digits)
            if not 0 <= n <= MASK: raise ProducerError("unsigned literal range")
            a = ("num", n)
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", t):
            a = ("var", t)
        else:
            raise ProducerError("expression")
        while self.peek() in PREC and PREC[self.peek()] >= minimum:
            op = self.take(); a = (op, a, self.expr(PREC[op] + 1))
        self.depth -= 1
        return a

    def block(self, nested: bool = False):
        self.take("{"); out = []
        if nested:
            self.depth += 1
            if self.depth > 64: raise ProducerError("block depth")
        while self.peek() != "}":
            t = self.peek()
            if t == "unsigned":
                if nested: raise ProducerError("nested declarations excluded")
                self.take(); name = self.ident(); self.take("=")
                e = self.expr(); self.take(";"); out.append(("decl", name, e))
            elif t == "if":
                self.take(); ident = self.branches; self.branches += 1
                if self.branches > 128: raise ProducerError("control bound")
                self.take("("); cond = self.expr(); self.take(")")
                yes = self.block(True); self.take("else"); no = self.block(True)
                out.append(("if", ident, cond, yes, no))
            elif t == "return":
                if nested: raise ProducerError("early return excluded")
                self.take(); e = self.expr(); self.take(";"); out.append(("ret", e))
                if self.peek() != "}": raise ProducerError("return must be final")
            else:
                name = self.ident(); self.take("="); e = self.expr(); self.take(";")
                out.append(("set", name, e))
        self.take("}")
        if nested: self.depth -= 1
        return out

    def program(self):
        self.take("unsigned"); self.take("f"); self.take("(")
        params = []
        if self.peek() != ")":
            while True:
                self.take("unsigned"); params.append(self.ident())
                if self.peek() != ",": break
                self.take(",")
        self.take(")")
        if not 1 <= len(params) <= 8 or len(set(params)) != len(params):
            raise ProducerError("parameter schema")
        body = self.block()
        if self.peek() != "<end>" or not body or body[-1][0] != "ret":
            raise ProducerError("function end")
        _validate_program_tree(body)
        return params, body


def value(op: str, args: tuple):
    if op == "not": return not args[0]
    if op == "inv": return (~args[0]) & MASK
    a, b = args
    if op == "+": return (a + b) & MASK
    if op == "-": return (a - b) & MASK
    if op == "*": return (a * b) & MASK
    if op == "/": return a // b if b else 0
    if op == "%": return a % b if b else 0
    if op == "<<": return (a << b) & MASK if b < 32 else 0
    if op == ">>": return a >> b if b < 32 else 0
    if op == "&": return a & b
    if op == "|": return a | b
    if op == "^": return a ^ b
    if op == "==": return a == b
    if op == "!=": return a != b
    if op == "<": return a < b
    if op == "<=": return a <= b
    if op == ">": return a > b
    if op == ">=": return a >= b
    raise ProducerError("term operator")

class DAG:
    def __init__(self, tick: Callable = _noop):
        self.nodes: list[tuple] = []
        self.index: dict[tuple, int] = {}
        self.fvs: list[frozenset] = []
        self.tick = tick
        self.true = self.const(True); self.false = self.const(False)

    def intern(self, key: tuple, fv: frozenset) -> int:
        if key in self.index: return self.index[key]
        if len(self.nodes) >= 2048: raise ProducerError("DAG bound")
        n = len(self.nodes); self.nodes.append(key); self.index[key] = n; self.fvs.append(fv)
        self.tick("symbolic_nodes")
        return n

    def const(self, val) -> int:
        # Keep bool and unsigned literals distinct; Python equates True with 1.
        return self.intern(("b" if type(val) is bool else "u", val), frozenset())

    def var(self, name: str) -> int:
        return self.intern(("input", name), frozenset({name}))

    def op(self, operator: str, *aa: int) -> int:
        if operator == "and":
            if self.false in aa: return self.false
            if aa[0] == self.true: return aa[1]
            if aa[1] == self.true or aa[0] == aa[1]: return aa[0]
        elif operator == "or":
            if self.true in aa: return self.true
            if aa[0] == self.false: return aa[1]
            if aa[1] == self.false or aa[0] == aa[1]: return aa[0]
        elif operator == "ite":
            if aa[0] == self.true: return aa[1]
            if aa[0] == self.false: return aa[2]
            if aa[1] == aa[2]: return aa[1]
        elif operator == "not":
            if aa[0] == self.true: return self.false
            if aa[0] == self.false: return self.true
            if self.nodes[aa[0]][0] == "not": return self.nodes[aa[0]][1]
        elif operator in {"==", "!=", "<=", ">=", "<", ">"} and aa[0] == aa[1]:
            return self.const(operator in {"==", "<=", ">="})
        if all(self.nodes[n][0] in {"b", "u"} for n in aa):
            vals = tuple(self.nodes[n][1] for n in aa)
            if operator == "and": v = vals[0] and vals[1]
            elif operator == "or": v = vals[0] or vals[1]
            elif operator == "ite": v = vals[1] if vals[0] else vals[2]
            else: v = value(operator, vals)
            return self.const(v)
        fv = frozenset().union(*(self.fvs[n] for n in aa))
        return self.intern((operator, *aa), fv)

    def evaluate(self, root: int, env: dict[str, int]):
        cache = {}
        def go(n):
            if n in cache: return cache[n]
            self.tick("producer_steps")
            op, *a = self.nodes[n]
            if op in {"b", "u"}: v = a[0]
            elif op == "input": v = env[a[0]]
            elif op == "and": v = go(a[0]) and go(a[1])
            elif op == "or": v = go(a[0]) or go(a[1])
            elif op == "ite": v = go(a[1]) if go(a[0]) else go(a[2])
            else: v = value(op, tuple(go(x) for x in a))
            cache[n] = v; return v
        return go(root)

@dataclass
class SymbolicProgram:
    output: int
    defined: int
    trace_events: list[tuple[int, int, int]]

class Translation:
    def __init__(self, dag: DAG, params: list[str]):
        self.d = dag
        self.params = params
        self.events = []

    def expression(self, e, env):
        d = self.d; op = e[0]
        if op == "num": return d.const(e[1]), d.true, "u"
        if op == "var":
            if e[1] not in env: raise ProducerError("uninitialized or undeclared variable")
            return env[e[1]], d.true, "u"
        if op in {"!", "~"}:
            a, ad, at = self.expression(e[1], env)
            if at != ("b" if op == "!" else "u"): raise ProducerError("unary type")
            return d.op("not" if op == "!" else "inv", a), ad, at
        a, ad, at = self.expression(e[1], env); b, bd, bt = self.expression(e[2], env)
        if op in {"&&", "||"}:
            if at != "b" or bt != "b": raise ProducerError("guard type")
            defined = d.op("and", ad, d.op("ite", a, bd, d.true) if op == "&&" else d.op("ite", a, d.true, bd))
            return d.op("and" if op == "&&" else "or", a, b), defined, "b"
        if at != "u" or bt != "u": raise ProducerError("numeric operand required")
        defined = d.op("and", ad, bd)
        if op in {"/", "%"}: defined = d.op("and", defined, d.op("!=", b, d.const(0)))
        if op in {"<<", ">>"}: defined = d.op("and", defined, d.op("<", b, d.const(32)))
        return d.op(op, a, b), defined, "b" if op in REL else "u"

    def block(self, stmts, env, path):
        d = self.d; env = dict(env); alive = d.true
        for st in stmts:
            if st[0] in {"decl", "set"}:
                tag, name, expr = st
                if (tag == "decl" and name in env) or (tag == "set" and name not in env):
                    raise ProducerError("variable declaration discipline")
                if len(env) >= 72 and tag == "decl": raise ProducerError("local bound")
                val, defined, typ = self.expression(expr, env)
                if typ != "u": raise ProducerError("assignment type")
                env[name] = val; alive = d.op("and", alive, defined)
            elif st[0] == "if":
                _, ident, guard, yes, no = st
                gv, gd, gt = self.expression(guard, env)
                if gt != "b": raise ProducerError("if requires Boolean grammar")
                ready = d.op("and", path, d.op("and", alive, gd))
                self.events.append((ident, ready, gv))
                ey, dy = self.block(yes, env, d.op("and", ready, gv))
                en, dn = self.block(no, env, d.op("and", ready, d.op("not", gv)))
                if set(ey) != set(en): raise ProducerError("branch environment")
                env = {n: d.op("ite", gv, ey[n], en[n]) for n in ey}
                alive = d.op("and", alive, d.op("and", gd, d.op("ite", gv, dy, dn)))
            else:
                raise ProducerError("statement placement")
        return env, alive

    def compile(self, source: str) -> SymbolicProgram:
        parsed = Parser(source); self.d.tick("producer_source_tokens", len(parsed.ts))
        names, body = parsed.program()
        if names != self.params: raise ProducerError("parameter order mismatch")
        env, alive = self.block(body[:-1], {n: self.d.var(n) for n in names}, self.d.true)
        out, defined, typ = self.expression(body[-1][1], env)
        if typ != "u": raise ProducerError("return type")
        return SymbolicProgram(out, self.d.op("and", alive, defined), self.events)

class Producer:
    def __init__(self, request: dict, tick: Callable = _noop):
        self.request = request
        self.names = list(request["inputs"])
        self.domains = request["inputs"]
        self.tick = tick
        self.dag = d = DAG(tick)
        self.programs = {role: Translation(d, self.names).compile(request[role])
                         for role in ("original", "candidate", "reference")}
        gp = Parser(request["repair_guard"]); tick("producer_source_tokens", len(gp.ts)); ge = gp.expr()
        if gp.peek() != "<end>": raise ProducerError("guard end")
        _validate_expression_tree(ge)
        try:
            gv, gd, gt = Translation(d, self.names).expression(ge, {n: d.var(n) for n in self.names})
        except RecursionError as exc:
            raise ProducerError("AST recursion safety") from exc
        if gt != "b" or gd != d.true: raise ProducerError("guard totality not simplified to true")
        p, q, r = (self.programs[k] for k in ("original", "candidate", "reference"))
        self.guard = gv
        repair = d.op("and", q.defined, d.op("and", r.defined, d.op("==", q.output, r.output)))
        preserve = d.op("and", q.defined, d.op("and", p.defined, d.op("==", q.output, p.output)))
        self.roots = [q.defined, d.op("or", d.op("not", gv), repair), d.op("or", gv, preserve)]
        # This is intentionally unsafe and used only as a labeled negative control.
        self.value_roots = [d.true, d.op("or", d.op("not", gv), d.op("==", q.output, r.output)),
                            d.op("or", gv, d.op("==", q.output, p.output))]

    def support(self, obligation: int, unsafe: bool = False) -> list[str]:
        root = (self.value_roots if unsafe else self.roots)[obligation]
        return [n for n in self.names if n in self.dag.fvs[root]]

    def points(self, support):
        for key in itertools.product(*(self.domains[n] for n in support)):
            self.tick("projected_points")
            env = {n: self.domains[n][0] for n in self.names}; env.update(zip(support, key))
            yield key, env

    def certificate(self, unsliced: bool = False) -> dict:
        parts = []
        for j, name in enumerate(IDS):
            sup = self.names[:] if unsliced else self.support(j)
            rows = []
            for key, env in self.points(sup):
                rows.append({"key": list(key), "ok": bool(self.dag.evaluate(self.roots[j], env))})
            parts.append({"obligation": name, "support": sup, "rows": rows})
        return {"kind": "finite-support-replay", "parts": parts}

    def trace(self, env) -> tuple:
        q = self.programs["candidate"]
        return tuple((i, int(self.dag.evaluate(g, env))) for i, reach, g in q.trace_events
                     if self.dag.evaluate(reach, env))

    def diagnostic(self, obligation: int, semantic_only: bool = False):
        s = set(self.support(obligation))
        if not semantic_only:
            for _, reach, g in self.programs["candidate"].trace_events:
                s.update(self.dag.fvs[reach]); s.update(self.dag.fvs[g])
        support = [n for n in self.names if n in s]
        best = None
        for _, env in self.points(support):
            if not self.dag.evaluate(self.roots[obligation], env):
                key = (self.trace(env), tuple(env[n] for n in self.names))
                self.tick("counterexample_comparisons")
                if best is None or key < best: best = key
        return None if best is None else {"obligation": IDS[obligation], "trace": [list(x) for x in best[0]], "input": list(best[1])}

    def unsafe_value_only_accepts(self) -> bool:
        # Enumerates only value dependencies, but replays the *real* predicates.
        # A missing definedness dependency can therefore hide a failure.
        for j in range(3):
            for _, env in self.points(self.support(j, unsafe=True)):
                if not self.dag.evaluate(self.roots[j], env): return False
        return True
