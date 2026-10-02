"""One-command clean reproduction of baseline, proof-DAG, and archive-audit evidence."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(command):
    completed=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=240,check=False,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'src')+os.pathsep+str(ROOT/'tests')})
    if completed.returncode:
        raise RuntimeError('command failed: '+' '.join(map(str,command))+'\n'+completed.stdout+'\n'+completed.stderr)
    return completed.stdout

def scientific_summary(obj):
    volatile={'generated_at_utc','peak_rss_kib','timing_ms','wall_seconds','isolated_wall_seconds'}
    def clean(value):
        if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k not in volatile}
        if isinstance(value,list): return [clean(v) for v in value]
        return value
    return clean(json.loads(json.dumps(obj)))

def reduced_cases(path):
    rows=json.loads(path.read_text())
    keep=('id','case','variant','status','witness','nodes','points','certificate_bytes')
    return [{k:r.get(k) for k in keep if k in r} for r in rows]

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args(); out=args.output.resolve()
    if out.exists() and any(out.iterdir()): parser.error('output must be new or empty')
    out.mkdir(parents=True,exist_ok=True); started=time.monotonic()
    baseline=out/'baseline'; structured=out/'structured'; holdout=out/'holdout-differential'
    # The three independent scientific campaigns run concurrently.  This uses at
    # most three local Python workers, stays below the documented four-core
    # budget, and avoids treating wall-clock serialization as scientific work.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'reproduce.py'),'--output',str(baseline)]),
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'structured_study.py'),'--output',str(structured)]),
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'holdout_differential.py'),'--output',str(holdout),'--cases','400']),
        ]
        for future in futures:
            future.result()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'proof_dag_security.py'),'--output',str(structured/'security-regression.json')]),
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'public_archive_audit.py'),'--output',str(structured/'codeflaws-archive-audit.json')]),
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'edge_case_regression.py'),'--output',str(structured/'edge-case-regression.json')]),
        ]
        for future in futures:
            future.result()
    # These gates consume requests from disk.  Authoritative coordinate order is
    # recovered from the deterministic fixture/stress generators and grammar
    # seeds, never from a certificate field.
    retained=ROOT/'proof-data'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'disk_replay.py'),
                             '--proof-data',str(structured),'--grammar-data',str(holdout),
                             '--output',str(structured/'disk-replay-audit.json')]),
            pool.submit(run,[sys.executable,str(ROOT/'tests'/'disk_replay.py'),
                             '--proof-data',str(retained),
                             '--output',str(out/'retained-disk-replay-audit.json')]),
        ]
        for future in futures:
            future.result()
    base_status=json.loads((baseline/'reproduction.json').read_text()); assert base_status['outcome']=='PASS_CLEAN_REPRODUCTION'
    baseline_study=json.loads((baseline/'study.json').read_text())
    study=json.loads((structured/'structured-study.json').read_text())
    audit=json.loads((structured/'codeflaws-archive-audit.json').read_text())
    security=json.loads((structured/'security-regression.json').read_text())
    edge=json.loads((structured/'edge-case-regression.json').read_text())
    disk_audit=json.loads((structured/'disk-replay-audit.json').read_text())
    retained_disk_audit=json.loads((out/'retained-disk-replay-audit.json').read_text())
    holdout_summary=json.loads((holdout/'summary.json').read_text())
    assert scientific_summary(study)==scientific_summary(json.loads((retained/'structured-study.json').read_text()))
    assert reduced_cases(structured/'fixture-cases.json')==reduced_cases(retained/'fixture-cases.json')
    assert reduced_cases(structured/'stress-cases.json')==reduced_cases(retained/'stress-cases.json')
    assert audit==json.loads((retained/'codeflaws-archive-audit.json').read_text())
    assert security==json.loads((retained/'security-regression.json').read_text())
    assert scientific_summary(edge)==scientific_summary(json.loads((retained/'edge-case-regression.json').read_text()))
    assert scientific_summary(disk_audit)==scientific_summary(json.loads((retained/'disk-replay-audit.json').read_text()))
    assert scientific_summary(retained_disk_audit)==scientific_summary(disk_audit)
    retained_holdout=retained/'holdout-differential'
    assert scientific_summary(holdout_summary)==scientific_summary(json.loads((retained_holdout/'summary.json').read_text()))
    assert (holdout/'cases.json').read_bytes()==(retained_holdout/'cases.json').read_bytes()
    assert sorted(p.name for p in (holdout/'inputs').iterdir())==sorted(p.name for p in (retained_holdout/'inputs').iterdir())
    for path in (retained_holdout/'inputs').iterdir():
        assert path.read_bytes()==(holdout/'inputs'/path.name).read_bytes(),path.name
    compared=0
    for dirname in ('fixture-inputs','fixture-certificates','stress-certificates','stress-inputs','controls','refutation-witnesses','refutation-controls'):
        before=retained/dirname; after=structured/dirname
        assert sorted(p.name for p in before.iterdir())==sorted(p.name for p in after.iterdir())
        for path in before.iterdir():
            assert path.read_bytes()==(after/path.name).read_bytes(),path.name; compared+=1
    result={'outcome':'PASS_COMPLETE_REPRODUCTION','baseline_compared_files':base_status['compared_files'],'proof_dag_byte_compared_files':compared,
            'structured_requests':study['total_requests'],'public_archive_records':audit['summary']['record_count'],
            'tamper_controls':study['tamper_attempts'],
            'native_defined_evaluations_per_compiler':baseline_study['native']['unique_defined_evaluations'],
            'native_compilers':baseline_study['native']['compilers'],
            'security_request_rejections':security['request_rejection_cases'],
            'security_certificate_type_rejections':security['certificate_type_rejection_cases'],
            'security_json_text_rejections':security['json_text_rejection_cases'],
            'operator_probes':security['operator_probes'],
            'disk_requests_reloaded':disk_audit['request_files_reloaded'],
            'disk_full_certificates_validated':disk_audit['full_vector_certificates_validated'],
            'disk_compact_certificates_validated':disk_audit['compact_refutation_certificates_validated'],
            'disk_grammar_results_validated':disk_audit['grammar_results_validated'],
            'producer_complexity_regression':edge['producer_complexity'],
            'left_deep_ast_regression':edge['left_deep_ast'],
            'selector_admission_regression':edge['selector_admission'],
            'holdout_differential_cases':holdout_summary['cases'],
            'holdout_oracle_agreements':holdout_summary['oracle_agreements'],
            'holdout_compact_refutations':holdout_summary['compact_refutations_verified'],
            'holdout_forged_refutations_rejected':holdout_summary['forged_refutations_rejected'],
            'wall_seconds':time.monotonic()-started,
            'scope_note':'Codeflaws evidence is an archival index audit; public sources are not executed by this command.'}
    (out/'complete-reproduction.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
