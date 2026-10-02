"""Local receiver-boundary regressions, separate from the 20-family study."""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from budget import Budget, enforce_limits
from checker import Session, check, decode, Invalid, Unsupported, Source
from producer import Producer, Parser, ProducerError
from fixture_oracle import request

M = 4294967295
DOMAIN = [0, 1, 31, 32, M]

def code(body):
    return 'unsigned f(unsigned x, unsigned y) { ' + body + ' }'

def obs(safe, value=None, path=()):
    return bool(safe), value if safe else None, tuple(path)

def oracle(i, x, y):
    if i == 1: return obs(True, (x+y*3)&M)
    if i == 2: return obs(y<32, ((x<<y)&M) if y<32 else None)
    if i == 3: return obs(y<32, (x>>y) if y<32 else None)
    if i == 4: return obs(y!=0, x//y if y else None)
    if i == 5: return obs(y!=0, x%y if y else None)
    if i == 6: return obs(y!=0, x)
    if i == 7: return obs(True, x if y==0 else x//y, [(0,int(y==0))])
    if i == 8:
        b = y!=0 and x//y>0
        return obs(True, int(b), [(0,int(b))])
    if i == 9:
        b = y==0 or x//y>0
        return obs(True, int(b), [(0,int(b))])
    if i == 10: return obs(y!=0, 1, [(0,1)] if y else [])
    if i == 11: return obs(y!=0, 1 if x==0 else 2, [(0,int(x==0))] if y else [])
    if i == 12: return obs(False)
    if i == 13: return obs(True, x, [(0,0)])
    if i == 14:
        b = y!=0 and x//y>0
        return obs(y!=0, int(b), [(0,int(b))] if y else [])
    if i == 15: return obs(True, (M^x)^(y&31))
    if i == 16: return obs(True, ((x+y*3)<<1)&M)
    if i == 17:
        b = x==0 or (y!=0 and x//y>0)
        return obs(True, int(b), [(0,int(b))])
    if i == 18:
        b = not (y==0 or not (x//y>0))
        return obs(True, int(b), [(0,int(b))])
    raise ValueError(i)

BODIES = [
 'return x + y * 3u;', 'return x << y;', 'return x >> y;',
 'return x / y;', 'return x % y;', 'unsigned q = x / y; return x;',
 'unsigned r=x; if (y==0u) {r=x;} else {r=x/y;} return r;',
 'unsigned r=0u; if ((y!=0u)&&(x/y>0u)) {r=1u;} else {r=0u;} return r;',
 'unsigned r=0u; if ((y==0u)||(x/y>0u)) {r=1u;} else {r=0u;} return r;',
 'unsigned r=0u; if (x/y==x/y) {r=1u;} else {r=1u;} return r;',
 'unsigned q=x/y; unsigned r=0u; if (x==0u) {r=1u;} else {r=2u;} return r;',
 'return x / (x ^ x);',
 'unsigned r=x; if (x<x) {r=1u/0u;} else {r=x;} return r;',
 'unsigned r=0u; if ((x/y>0u)&&(y!=0u)) {r=1u;} else {r=0u;} return r;',
 'return ~x ^ (y & 31u);', 'return x + y * 3u << 1u;',
 'unsigned r=0u; if ((x==0u)||(y!=0u)&&(x/y>0u)) {r=1u;} else {r=0u;} return r;',
 'unsigned r=0u; if (!((y==0u)||(!(x/y>0u)))) {r=1u;} else {r=0u;} return r;',
]

def run(budget):
    semantic = []
    for i, body in enumerate(BODIES, 1):
        req = {'id':f'boundary-{i:02d}', 'word_bits':32,
               'inputs':{'x':DOMAIN, 'y':DOMAIN}, 'original':code('return x;'),
               'candidate':code(body), 'reference':code('return x;'), 'repair_guard':'x==x'}
        p = Producer(req, budget.tick); cert=p.certificate(); s=Session(req, budget.tick)
        rows=[]
        for x,y in itertools.product(DOMAIN, repeat=2):
            budget.tick('boundary_oracle_rows'); env={'x':x,'y':y}
            safe,val,path=oracle(i,x,y); actual=s.run('candidate',env)
            assert actual==(safe,val,path), (i,x,y,actual,(safe,val,path))
            truth=[safe,safe and val==x,True]
            assert [s.predicate(j,env) for j in range(3)]==truth
            assert [bool(p.dag.evaluate(root,env)) for root in p.roots]==truth
            assert p.trace(env)==path
            rows.append({'input':[x,y],'trace':[list(t) for t in path],'truth':truth})
        expected=None
        for j,label in enumerate(('defined','repair','preserve')):
            bad=[r for r in rows if not r['truth'][j]]
            if bad:
                row=min(bad,key=lambda r:(r['trace'],r['input']))
                expected={'obligation':label,'trace':row['trace'],'input':row['input']}; break
        checked=s.check(cert)
        assert checked['witness']==expected
        assert checked['status']==('ACCEPT' if expected is None else 'REFUTED')
        semantic.append({'id':req['id'],'request':req,'certificate':cert,'oracle':rows,'result':checked})
    # Rejection before admission: no malformed source is executed natively.
    keywords=('auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert _Thread_local').split()
    bad_sources = [('reserved-'+k,code('unsigned '+k+'=1u; return x;')) for k in keywords]
    bad_sources += [
        ('reserved-double-underscore',code('unsigned __value=1u; return x;')),
        ('reserved-underscore-uppercase',code('unsigned _Value=1u; return x;')),
        ('line-splice',code('return x;')+' // comment \\\n'),
        ('trigraph',code('return x;')+' // ??/\n'),
        ('unicode-space',code('return\u00a0x;')),
        ('control-space',code('return\x1cx;')),
        ('octal-like',code('return 01u;')),
        ('plain-literal',code('return 1;')),
        ('array',code('unsigned a[2]; return x;')),
        ('loop',code('while (x>0u) {x=x-1u;} return x;')),
        ('call',code('return g(x);')),
        ('early-return',code('if(x==0u){return x;}else{x=x;} return x;')),
        ('uninitialized',code('unsigned r=r; return r;')),
        ('duplicate-local',code('unsigned r=x; unsigned r=y; return r;')),
        ('numeric-guard',code('unsigned r=x; if(x){r=y;}else{r=x;} return r;')),
        ('unterminated-comment',code('return x;')+' /*'),
    ]
    base = {'id':'syntax-control','word_bits':32,'inputs':{'x':[0,1],'y':[0,1]},
            'original':code('return x;'),'candidate':code('return x;'),
            'reference':code('return x;'),'repair_guard':'x==x'}
    clean=Producer(base,budget.tick).certificate(); rejects=[]
    for name,source in bad_sources:
        budget.tick('syntax_controls'); req=dict(base); req['candidate']=source
        result=check(req,clean,budget.tick)
        assert result['status'] in {'UNKNOWN','INVALID'}, (name,result)
        try: Parser(source).program()
        except (ProducerError,RecursionError): pass
        else:
            # Parser alone deliberately does not perform declaration/type analysis.
            try: Producer(req,budget.tick)
            except (ProducerError,RecursionError): pass
            else: raise AssertionError(('producer admitted source',name))
        rejects.append({'id':name,'source':source,'result':result})
    bad_json=['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":-Infinity}','{"a":1,}']
    for text in bad_json:
        budget.tick('json_controls')
        try: decode(text)
        except Invalid: pass
        else: raise AssertionError(('invalid JSON admitted',text))
    request_controls=[]
    for name,field,val in [('non-string-input','inputs',{1:[0]}),('boolean-domain','inputs',{'x':[False],'y':[0]}),
                           ('domain-order','inputs',{'x':[1,0],'y':[0]}),('boolean-width','word_bits',True)]:
        req=dict(base); req[field]=val; budget.tick('request_controls')
        result=check(req,clean,budget.tick)
        assert result['status'] in {'INVALID','UNKNOWN'}, (name,result)
        request_controls.append({'id':name,'result':result})
    return {'outcome':'PASS_LOCAL_REGRESSIONS','semantic_cases':semantic,'syntax_controls':rejects,
            'invalid_json_controls':len(bad_json),'request_controls':request_controls,
            'totals':{'semantic_cases':len(semantic),'semantic_oracle_rows':25*len(semantic),
                      'syntax_controls':len(rejects),'invalid_json_controls':len(bad_json),
                      'request_controls':len(request_controls),'disagreements':0}}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'results'/'regression.json')
    args=p.parse_args(); enforce_limits(); b=Budget(200_000); report={'outcome':'FAILED'}
    try: report=run(b)
    except Exception as e:
        report['error']=type(e).__name__+': '+str(e); report['traceback']=traceback.format_exc(); raise
    finally:
        report['resources']=b.report(); args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in {'semantic_cases','syntax_controls','request_controls'}},indent=2))
if __name__=='__main__': main()
