"""Fresh-receiver comparison with and without replay-table certificates."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from budget import Budget,enforce_limits
from checker import Session,decode,OBLIGATIONS
from fixture_oracle import least_violation

class Meter:
    def __init__(self,budget): self.budget=budget; self.counts=collections.Counter()
    def tick(self,kind,n=1): self.budget.tick(kind,n); self.counts[kind]+=n

def direct(session):
    failures=[]; checked=0
    for j in range(3):
        support=[n for n in session.names if n in session.required[j]]
        for _,values in session.cells(support):
            checked+=1
            if not session.predicate(j,values) and j not in failures: failures.append(j)
    return {'status':'REFUTED' if failures else 'ACCEPT',
            'witness':session.canonical(failures[0]) if failures else None,'checked_rows':checked}

def run(budget, results, partial, context_path, resume=False):
    sources = {name: (ROOT/'src'/name).read_text() for name in ('checker.py','budget.py')}
    sources['control'] = Path(__file__).read_text()
    context = {'sources': sources, 'inputs': {}, 'certificates': {}, 'oracles': {}}
    for path in sorted((ROOT/'inputs').glob('fixture-*.json')):
        key = path.stem
        context['inputs'][key] = path.read_text()
        context['certificates'][key] = (results/'certificates'/(key+'.json')).read_text()
        context['oracles'][key] = (results/'oracle'/(key+'.json')).read_text()
    if resume:
        if json.loads(context_path.read_text()) != context:
            raise ValueError('resume context differs; do not mix code, requests, or evidence')
        records = json.loads(partial.read_text())['records']
    else:
        records = []
        context_path.write_text(json.dumps(context)+'\n')
    completed = {r['id'] for r in records}
    for req_path in sorted((ROOT/'inputs').glob('fixture-*.json')):
        request=decode(req_path.read_text()); identifier=request['id']
        if identifier in completed: continue
        cert=decode((results/'certificates'/(identifier+'.json')).read_text())
        oracle=json.loads((results/'oracle'/(identifier+'.json')).read_text())
        budget.tick('null_requests'); expected=least_violation(oracle)
        certified_meter=Meter(budget); certified=Session(request,certified_meter.tick).check(cert)
        direct_meter=Meter(budget); unchecked=direct(Session(request,direct_meter.tick))
        for result in (certified,unchecked):
            assert result['status']==('ACCEPT' if expected is None else 'REFUTED')
            assert result['witness']==expected
        records.append({'id':identifier,'status':certified['status'],'witness':expected,
                        'certificate_rows':certified['checked_rows'],'direct_rows':unchecked['checked_rows'],
                        'certificate_arm':dict(sorted(certified_meter.counts.items())),
                        'receiver_only_arm':dict(sorted(direct_meter.counts.items()))})
        temporary = partial.with_suffix('.tmp')
        temporary.write_text(json.dumps({'records':records,'resources':budget.report()})+'\n')
        temporary.replace(partial)
    assert len(records)==80
    categories=set().union(*(r['certificate_arm'] for r in records),*(r['receiver_only_arm'] for r in records))
    sums={arm:{k:sum(r[arm].get(k,0) for r in records) for k in sorted(categories)}
          for arm in ('certificate_arm','receiver_only_arm')}
    return {'outcome':'PASS_NULL_CONTROL','records':records,'totals':{
            'requests':len(records),'matching_results':len(records),
            'equal_replay_rows':sum(r['certificate_rows']==r['direct_rows'] for r in records),
            'equal_source_interpreter_steps':sum(r['certificate_arm'].get('checker_steps',0)==r['receiver_only_arm'].get('checker_steps',0) for r in records),
            'certificate_rows':sum(r['certificate_rows'] for r in records),
            'direct_rows':sum(r['direct_rows'] for r in records)},'aggregate_counts':sums,
            'interpretation':'This replay-table format is not necessary: the receiver independently derives and evaluates the same projected obligations without receiving a certificate.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'results')
    p.add_argument('--output',type=Path,default=ROOT/'results'/'null-control.json')
    p.add_argument('--resume',action='store_true',help='resume only a byte-identical saved context')
    a=p.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    partial=a.output.with_suffix('.partial.json'); context_path=a.output.with_suffix('.context.json')
    enforce_limits(); budget=Budget(240_000); result={'outcome':'FAILED'}
    try:
        result=run(budget,a.results,partial,context_path,a.resume)
        partial.unlink(missing_ok=True); context_path.unlink(missing_ok=True)
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e); result['traceback']=traceback.format_exc(); raise
    finally:
        result['resources']=budget.report(); a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
if __name__=='__main__': main()
