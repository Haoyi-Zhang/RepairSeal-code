"""Independent checker for finite semantic proof DAG certificates.

This module intentionally imports neither ``producer`` nor
``proof_dag_producer``.  It has a separate scanner/parser/circuit compiler and
checks every semantic-vector cell by a local rule.  It is a tested reference
checker, not a mechanically verified checker.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MASK = (1 << 32) - 1
SCHEMA = "finite-semantic-proof-dag-v1"
ROLES = ("original", "candidate", "reference")
OBLIGATIONS = ("defined", "repair", "preserve")
MAX_BINDINGS = 72  # At most 8 parameters plus enough outer-block locals to total 72 names.
MAX_DOMAIN_VALUES = 64
MAX_AST_DEPTH = 64
MAX_AST_NODES = 4096
MAX_LITERAL_DIGITS = 10
ARITH = {"+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"}
REL = {"==", "!=", "<", "<=", ">", ">="}
RESERVED = set("auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local".split())
PREC = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
        "==": 6, "!=": 6, "<": 7, "<=": 7, ">": 7, ">=": 7,
        "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}

class Invalid(ValueError): pass
class Unsupported(ValueError): pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def exact_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON-shaped values without Python's bool/int aliasing.

    Python deliberately treats ``True == 1`` and ``False == 0``.  Certificate
    binding is stricter than ordinary Python equality: a JSON Boolean is not a
    JSON number, including inside nested lists and dictionaries.  Keeping this
    comparison small and local also makes every certificate-to-reconstruction
    boundary explicit.
    """
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(
            exact_equal(actual[key], expected[key]) for key in expected
        )
    if type(expected) in {list, tuple}:
        return len(actual) == len(expected) and all(
            exact_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def load_json_strict(text: str) -> Any:
    """Decode JSON while rejecting duplicate keys and non-finite constants."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Invalid("duplicate JSON key")
            result[key] = value
        return result

    def bad_constant(_value: str):
        raise Invalid("non-finite JSON number")

    try:
        return json.loads(text, object_pairs_hook=object_pairs, parse_constant=bad_constant)
    except Invalid:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Invalid("JSON syntax") from exc


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _validate_expression_tree(root) -> tuple[int, int]:
    """Measure the real tuple-AST without recursive host-language traversal."""
    stack = [(root, 1)]
    nodes = 0
    maximum = 0
    while stack:
        expr, depth = stack.pop()
        nodes += 1
        maximum = max(maximum, depth)
        if depth > MAX_AST_DEPTH:
            raise Unsupported("AST depth")
        if nodes > MAX_AST_NODES:
            raise Unsupported("AST node bound")
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
            raise Unsupported("AST statement")
        for expression in expressions:
            count, depth = _validate_expression_tree(expression)
            total += count
            maximum = max(maximum, depth)
            if total > MAX_AST_NODES:
                raise Unsupported("AST node bound")
    return total, maximum

class Reader:
    def __init__(self, source: str):
        if type(source) is not str or len(source) > 16384 or len(source.splitlines()) > 250:
            raise Unsupported("source bound")
        if "\\" in source or "??" in source or any(c not in " \t\r\n\v\f" and not 32 <= ord(c) <= 126 for c in source):
            raise Unsupported("preprocessing/non-ASCII excluded")
        source = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
        pattern = re.compile(r"[ \t\r\n\v\f]+|[A-Za-z_][A-Za-z_0-9]*|[0-9]+u|==|!=|<=|>=|<<|>>|&&|\|\||[{}(),;=+*/%&|^<>!~\-]")
        self.tokens = []
        at = 0
        while at < len(source):
            match = pattern.match(source, at)
            if match is None: raise Unsupported("token outside fragment")
            token = match.group(0)
            if not token.isspace(): self.tokens.append(token)
            at = match.end()
        if len(self.tokens) > 4096: raise Unsupported("token bound")
        self.at = 0; self.branches = 0; self.depth = 0
    def peek(self): return self.tokens[self.at] if self.at < len(self.tokens) else "<end>"
    def take(self, expected=None):
        token = self.peek()
        if token == "<end>" or expected is not None and token != expected: raise Unsupported("grammar mismatch")
        self.at += 1; return token
    def name(self):
        token = self.take()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", token) or token in RESERVED or token.startswith("__") or token.startswith("_") and len(token)>1 and token[1].isupper():
            raise Unsupported("identifier")
        return token
    def expression(self, minimum=1):
        self.depth += 1
        if self.depth > 64: raise Unsupported("expression depth")
        token = self.take()
        if token == "(": value = self.expression(); self.take(")")
        elif token in {"!", "~"}: value = (token, self.expression(11))
        elif re.fullmatch(r"[0-9]+u", token):
            digits = token[:-1]
            if len(digits) > MAX_LITERAL_DIGITS: raise Unsupported("literal length")
            if len(token)>2 and token[0]=="0": raise Unsupported("octal")
            number = int(digits)
            if number > MASK: raise Unsupported("literal")
            value = ("num", number)
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", token): value = ("var", token)
        else: raise Unsupported("expression")
        while self.peek() in PREC and PREC[self.peek()] >= minimum:
            op = self.take(); value = (op, value, self.expression(PREC[op] + 1))
        self.depth -= 1; return value
    def block(self, nested=False):
        self.take("{"); result=[]
        if nested:
            self.depth += 1
            if self.depth > 64: raise Unsupported("block depth")
        while self.peek() != "}":
            token = self.peek()
            if token == "unsigned":
                if nested: raise Unsupported("nested declaration")
                self.take(); name=self.name(); self.take("="); expr=self.expression(); self.take(";"); result.append(("decl",name,expr))
            elif token == "if":
                self.take(); site=self.branches; self.branches += 1
                if self.branches > 128: raise Unsupported("branch bound")
                self.take("("); cond=self.expression(); self.take(")")
                yes=self.block(True); self.take("else"); no=self.block(True); result.append(("if",site,cond,yes,no))
            elif token == "return":
                if nested: raise Unsupported("early return")
                self.take(); expr=self.expression(); self.take(";"); result.append(("ret",expr))
                if self.peek() != "}": raise Unsupported("return placement")
            else:
                name=self.name(); self.take("="); expr=self.expression(); self.take(";"); result.append(("set",name,expr))
        self.take("}")
        if nested: self.depth -= 1
        return result
    def program(self):
        self.take("unsigned"); self.take("f"); self.take("("); params=[]
        if self.peek() != ")":
            while True:
                self.take("unsigned"); params.append(self.name())
                if self.peek() != ",": break
                self.take(",")
        self.take(")")
        if not 1 <= len(params) <= 8 or len(set(params)) != len(params): raise Unsupported("parameters")
        body=self.block()
        if self.peek() != "<end>" or not body or body[-1][0] != "ret": raise Unsupported("function end")
        _validate_program_tree(body)
        return params, body

class Circuit:
    def __init__(self):
        self.nodes=[]; self.index={}; self.sorts=[]
        self.true=self.const(True); self.false=self.const(False)
    def intern(self, key, sort):
        if key in self.index: return self.index[key]
        if len(self.nodes) >= 2048: raise Unsupported("circuit bound")
        index=len(self.nodes); self.nodes.append(key); self.sorts.append(sort); self.index[key]=index; return index
    def const(self, value): return self.intern(("b" if type(value) is bool else "u", value), "bool" if type(value) is bool else "u32")
    def input(self, name): return self.intern(("input", name), "u32")
    def op(self, operator, *children):
        if operator == "and":
            if self.false in children: return self.false
            if children[0] == self.true: return children[1]
            if children[1] == self.true or children[0] == children[1]: return children[0]
        elif operator == "or":
            if self.true in children: return self.true
            if children[0] == self.false: return children[1]
            if children[1] == self.false or children[0] == children[1]: return children[0]
        elif operator == "ite":
            if children[0] == self.true: return children[1]
            if children[0] == self.false: return children[2]
            if children[1] == children[2]: return children[1]
        elif operator == "not":
            if children[0] == self.true: return self.false
            if children[0] == self.false: return self.true
            if self.nodes[children[0]][0] == "not": return self.nodes[children[0]][1]
        elif operator in REL and children[0] == children[1]: return self.const(operator in {"==", "<=", ">="})
        if all(self.nodes[c][0] in {"b", "u"} for c in children):
            vals=tuple(self.nodes[c][1] for c in children)
            return self.const(local_value(operator, vals))
        sort = self.sorts[children[1]] if operator == "ite" else ("bool" if operator in {"and","or","not"}|REL else "u32")
        return self.intern((operator,*children), sort)

@dataclass
class Compiled:
    output:int
    defined:int
    events:list[tuple[int,int,int]]

class Elaborator:
    def __init__(self,circuit,params): self.c=circuit; self.params=params; self.events=[]
    def expr(self,e,env):
        c=self.c; op=e[0]
        if op=="num": return c.const(e[1]),c.true,"u"
        if op=="var":
            if e[1] not in env: raise Unsupported("uninitialized")
            return env[e[1]],c.true,"u"
        if op in {"!","~"}:
            value,defined,typ=self.expr(e[1],env)
            if typ != ("b" if op=="!" else "u"): raise Unsupported("unary type")
            return c.op("not" if op=="!" else "inv",value),defined,typ
        left,ld,lt=self.expr(e[1],env); right,rd,rt=self.expr(e[2],env)
        if op in {"&&","||"}:
            if lt!="b" or rt!="b": raise Unsupported("logical type")
            defined=c.op("and",ld,c.op("ite",left,rd,c.true) if op=="&&" else c.op("ite",left,c.true,rd))
            return c.op("and" if op=="&&" else "or",left,right),defined,"b"
        if lt!="u" or rt!="u": raise Unsupported("numeric type")
        defined=c.op("and",ld,rd)
        if op in {"/","%"}: defined=c.op("and",defined,c.op("!=",right,c.const(0)))
        if op in {"<<",">>"}: defined=c.op("and",defined,c.op("<",right,c.const(32)))
        return c.op(op,left,right),defined,"b" if op in REL else "u"
    def block(self,stmts,env,path):
        c=self.c; env=dict(env); alive=c.true
        for st in stmts:
            if st[0] in {"decl","set"}:
                tag,name,expr=st
                if tag=="decl" and name in env or tag=="set" and name not in env: raise Unsupported("declaration discipline")
                if tag=="decl" and len(env) >= MAX_BINDINGS: raise Unsupported("local variable bound")
                value,defined,typ=self.expr(expr,env)
                if typ!="u": raise Unsupported("assignment type")
                env[name]=value; alive=c.op("and",alive,defined)
            elif st[0]=="if":
                _,site,guard,yes,no=st; gv,gd,gt=self.expr(guard,env)
                if gt!="b": raise Unsupported("if type")
                ready=c.op("and",path,c.op("and",alive,gd)); self.events.append((site,ready,gv))
                ey,dy=self.block(yes,env,c.op("and",ready,gv)); en,dn=self.block(no,env,c.op("and",ready,c.op("not",gv)))
                if set(ey)!=set(en): raise Unsupported("branch environment")
                env={name:c.op("ite",gv,ey[name],en[name]) for name in ey}
                alive=c.op("and",alive,c.op("and",gd,c.op("ite",gv,dy,dn)))
            else: raise Unsupported("statement placement")
        return env,alive
    def compile(self,source):
        reader=Reader(source); names,body=reader.program()
        if names!=self.params: raise Invalid("parameter order")
        env,alive=self.block(body[:-1],{n:self.c.input(n) for n in names},self.c.true)
        value,defined,typ=self.expr(body[-1][1],env)
        if typ!="u": raise Unsupported("return type")
        return Compiled(value,self.c.op("and",alive,defined),self.events)

def local_value(op,args):
    if op=="not": return not args[0]
    if op=="inv": return (~args[0]) & MASK
    if op=="and": return bool(args[0] and args[1])
    if op=="or": return bool(args[0] or args[1])
    if op=="ite": return args[1] if args[0] else args[2]
    a,b=args
    if op=="+": return (a+b)&MASK
    if op=="-": return (a-b)&MASK
    if op=="*": return (a*b)&MASK
    if op=="/": return a//b if b else 0
    if op=="%": return a%b if b else 0
    if op=="<<": return (a<<b)&MASK if b<32 else 0
    if op==">>": return a>>b if b<32 else 0
    if op=="&": return a&b
    if op=="|": return a|b
    if op=="^": return a^b
    if op=="==": return a==b
    if op=="!=": return a!=b
    if op=="<": return a<b
    if op=="<=": return a<=b
    if op==">": return a>b
    if op==">=": return a>=b
    raise Invalid("operator")

def build_expected(request):
    try:
        names=list(request["inputs"]); c=Circuit()
        programs={role:Elaborator(c,names).compile(request[role]) for role in ROLES}
        reader=Reader(request["repair_guard"]); guard_expr=reader.expression()
        if reader.peek()!="<end>": raise Invalid("guard end")
        _validate_expression_tree(guard_expr)
        guard,defined,typ=Elaborator(c,names).expr(guard_expr,{n:c.input(n) for n in names})
        if typ!="b" or defined!=c.true: raise Unsupported("guard totality not simplified to true")
        p,q,r=(programs[k] for k in ROLES)
        repair=c.op("and",q.defined,c.op("and",r.defined,c.op("==",q.output,r.output)))
        preserve=c.op("and",q.defined,c.op("and",p.defined,c.op("==",q.output,p.output)))
        roots=[q.defined,c.op("or",c.op("not",guard),repair),c.op("or",guard,preserve)]
        # The untrusted producer also materializes its explicitly labelled unsafe
        # value-only negative-control roots.  They are not trusted as obligations,
        # but reconstructing them keeps the canonical circuit/source binding exact.
        c.op("or",c.op("not",guard),c.op("==",q.output,r.output))
        c.op("or",guard,c.op("==",q.output,p.output))
        return c,programs,guard,roots
    except RecursionError as exc:
        raise Unsupported("AST recursion safety") from exc

def _expected_record(index,key,sort):
    op,*args=key; base={"id":index,"op":op,"sort":sort}
    if op in {"b","u","input"}: base["data"]=args[0]
    else: base["children"]=list(args)
    return base

def validate_request_fields(request:dict):
    """Validate the receiver-owned request without enumerating its product."""
    required={"id","word_bits","inputs","original","candidate","reference","repair_guard"}
    if type(request) is not dict or set(request)!=required: raise Invalid("request schema")
    if type(request["id"]) is not str or not request["id"] or len(request["id"])>64: raise Invalid("request identifier")
    if type(request["word_bits"]) is not int or request["word_bits"]!=32: raise Unsupported("word width")
    domains=request["inputs"]
    if type(domains) is not dict or not 1<=len(domains)<=8: raise Invalid("input schema")
    for name,values in domains.items():
        if type(name) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",name) or name in RESERVED or name.startswith("__") or name.startswith("_") and len(name)>1 and name[1].isupper(): raise Invalid("input name")
        if type(values) is not list or not 1<=len(values)<=MAX_DOMAIN_VALUES: raise Invalid("domain")
        if any(type(v)is not int or type(v)is bool or not 0<=v<=MASK for v in values): raise Invalid("domain")
        if values!=sorted(values) or len(set(values))!=len(values): raise Invalid("domain")
    if math.prod(map(len,domains.values()))>4096: raise Unsupported("domain bound")
    for field in (*ROLES,"repair_guard"):
        if type(request[field]) is not str: raise Invalid("source type")
    names=list(domains)
    return domains,names


def validate_request(request:dict):
    """Validate the receiver-owned request and enumerate canonical points."""
    domains,names=validate_request_fields(request)
    points=[list(p) for p in itertools.product(*(domains[n] for n in names))]
    return domains,names,points


def trace_from_vectors(events, vectors, point_index):
    out=[]
    for site,reachable,guard in events:
        if vectors[reachable][point_index]:
            out.append([site,int(bool(vectors[guard][point_index]))])
    return out


def classify_vectors(points, roots, events, vectors):
    failing=None
    for obligation,root in zip(OBLIGATIONS,roots):
        bad=[i for i,v in enumerate(vectors[root]) if not v]
        if bad:
            i=min(bad,key=lambda j:(trace_from_vectors(events,vectors,j),points[j]))
            failing={"obligation":obligation,"trace":trace_from_vectors(events,vectors,i),"input":points[i]}
            break
    return {"status":"ACCEPT" if failing is None else "REFUTED","witness":failing}


def evaluate_topological(request:dict,count:Callable[[str,int],None]|None=None):
    """Certificate-free DAG evaluation with one computation per node and point.

    This is the strongest obvious baseline for an explicit full-vector
    certificate: it reparses the authoritative source and computes the same
    canonical circuit topologically without receiving producer evidence.
    """
    tick=count or (lambda _kind,_n=1:None)
    _domains,names,points=validate_request(request)
    circuit,programs,_guard,roots=build_expected(request)
    positions={name:i for i,name in enumerate(names)}
    vectors=[]
    for key in circuit.nodes:
        op=key[0]; vector=[]
        for cell,point in enumerate(points):
            tick("topological_cells",1)
            if op in {"b","u"}: value=key[1]
            elif op=="input": value=point[positions[key[1]]]
            else: value=local_value(op,tuple(vectors[ch][cell] for ch in key[1:]))
            vector.append(value)
        vectors.append(vector)
    result=classify_vectors(points,roots,programs["candidate"].events,vectors)
    result.update({"checked_nodes":len(circuit.nodes),"checked_cells":len(circuit.nodes)*len(points),"mode":"topological-direct"})
    return result


def check(request:dict,certificate:dict,count:Callable[[str,int],None]|None=None,mode="proof"):
    tick=count or (lambda _kind,_n=1:None)
    domains,names,points=validate_request(request)
    if type(certificate) is not dict: raise Invalid("certificate type")
    fields={"kind","request_id","word_bits","input_order","domains","points","source_sha256","nodes","role_roots","guard_root","obligation_roots","certificate_sha256"}
    if set(certificate)!=fields or certificate["kind"]!=SCHEMA: raise Invalid("certificate schema")
    supplied_hash=certificate["certificate_sha256"]
    if type(supplied_hash) is not str or not re.fullmatch(r"[0-9a-f]{64}",supplied_hash): raise Invalid("certificate digest format")
    unhashed=dict(certificate); del unhashed["certificate_sha256"]
    if supplied_hash!=hashlib.sha256(canonical_bytes(unhashed)).hexdigest(): raise Invalid("certificate digest")
    if not exact_equal(certificate["request_id"],request["id"]) or not exact_equal(certificate["word_bits"],32) or not exact_equal(certificate["input_order"],names) or not exact_equal(certificate["domains"],domains) or not exact_equal(certificate["points"],points): raise Invalid("request/domain binding")
    hashes={role:digest(request[role]) for role in ROLES}|{"repair_guard":digest(request["repair_guard"])}
    if not exact_equal(certificate["source_sha256"],hashes): raise Invalid("source binding")
    circuit,programs,guard,roots=build_expected(request)
    expected_roles={role:{"output":programs[role].output,"defined":programs[role].defined,"trace_events":[{"site":s,"reachable":r,"guard":g} for s,r,g in programs[role].events]} for role in ROLES}
    if not exact_equal(certificate["role_roots"],expected_roles) or not exact_equal(certificate["guard_root"],guard) or not exact_equal(certificate["obligation_roots"],dict(zip(OBLIGATIONS,roots))): raise Invalid("root binding")
    nodes=certificate["nodes"]
    if type(nodes)is not list or len(nodes)!=len(circuit.nodes): raise Invalid("node count")
    verified=[]
    for index,(record,key,sort) in enumerate(zip(nodes,circuit.nodes,circuit.sorts)):
        expected=_expected_record(index,key,sort)
        if type(record)is not dict or set(record)!=(set(expected)|{"vector"}): raise Invalid(f"node {index} schema")
        if any(not exact_equal(record[k],v) for k,v in expected.items()): raise Invalid(f"node {index} topology")
        vector=record["vector"]
        if type(vector)is not list or len(vector)!=len(points): raise Invalid(f"node {index} vector length")
        computed=[]
        op=key[0]
        # These addresses depend only on the independently reconstructed node,
        # not on submitted topology. Keep every cell calculation and check.
        input_position=names.index(key[1]) if op=="input" else None
        children=key[1:] if op not in {"b","u","input"} else ()
        child_vectors=tuple(verified[ch] for ch in children) if mode=="proof" else ()
        arity=len(child_vectors)
        for cell,point in enumerate(points):
            tick("proof_cells",1)
            if op=="b" or op=="u": value=key[1]
            elif op=="input": value=point[input_position]
            else:
                if mode=="proof":
                    if arity==1: args=(child_vectors[0][cell],)
                    elif arity==2: args=(child_vectors[0][cell],child_vectors[1][cell])
                    else: args=(child_vectors[0][cell],child_vectors[1][cell],child_vectors[2][cell])
                elif mode=="rebuild": args=tuple(_recompute(circuit,ch,point,names,tick) for ch in children)
                else: raise ValueError("mode")
                value=local_value(op,args)
            if sort=="bool":
                if type(vector[cell]) is not bool: raise Invalid(f"node {index} sort")
            elif type(vector[cell]) is not int or type(vector[cell]) is bool or not 0<=vector[cell]<=MASK: raise Invalid(f"node {index} sort")
            if vector[cell]!=value: raise Invalid(f"node {index} cell {cell} mismatch")
            computed.append(value)
        verified.append(computed)
    result=classify_vectors(points,roots,programs["candidate"].events,verified)
    result.update({"checked_nodes":len(nodes),"checked_cells":len(nodes)*len(points),"mode":mode})
    return result

def _recompute(circuit,node,point,names,tick):
    tick("rebuild_cells",1); key=circuit.nodes[node]; op=key[0]
    if op in {"b","u"}: return key[1]
    if op=="input": return point[names.index(key[1])]
    return local_value(op,tuple(_recompute(circuit,ch,point,names,tick) for ch in key[1:]))

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("request",type=Path); parser.add_argument("certificate",type=Path); parser.add_argument("--mode",choices=["proof","rebuild"],default="proof")
    args=parser.parse_args()
    try:
        request=load_json_strict(args.request.read_text())
        certificate=load_json_strict(args.certificate.read_text())
        result=check(request,certificate,mode=args.mode)
    except (Invalid,Unsupported) as exc: result={"status":"INVALID","reason":str(exc)}
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
