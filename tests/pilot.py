"""Bounded, single-worker discriminating pilot for fixture 17."""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from budget import Budget, enforce_limits
from producer import Producer
from checker import Session, check
from fixture_oracle import request, exhaustive, least_violation, least_hole, VARIANTS

def main():
    enforce_limits(); budget = Budget(operation_limit=250_000)
    report = {'case': 17, 'variants': [], 'outcome': 'FAILED'}
    try:
        for variant in VARIANTS:
            req = request(17, variant)
            oracle = exhaustive(17, variant); budget.tick('oracle_rows', len(oracle))
            p = Producer(req, budget.tick); cert = p.certificate()
            got = check(req, cert, budget.tick)
            expected = least_violation(oracle)
            assert got['status'] == ('ACCEPT' if expected is None else 'REFUTED'), got
            assert got['witness'] == expected, (got, expected)
            session = Session(req, budget.tick)
            for row in oracle:
                env = dict(zip(session.names, row['input']))
                assert [session.predicate(j, env) for j in range(3)] == row['truth']
                assert [list(t) for t in session.run('candidate', env)[2]] == row['trace']
                assert [bool(p.dag.evaluate(root, env)) for root in p.roots] == row['truth']
                assert [list(t) for t in p.trace(env)] == row['trace']
            record = {'variant': variant, 'status': got['status'], 'witness': got['witness'],
                      'certificate_rows': sum(len(x['rows']) for x in cert['parts']),
                      'dag_nodes': len(p.dag.nodes), 'checker_nodes': session.symbols,
                      'unsafe_value_only_accepts': p.unsafe_value_only_accepts()}
            if expected:
                j = ('defined','repair','preserve').index(expected['obligation'])
                record['semantic_only_diagnostic'] = p.diagnostic(j, semantic_only=True)
                record['trace_aware_diagnostic'] = p.diagnostic(j)
                assert record['trace_aware_diagnostic'] == expected
            else:
                partial = json.loads(json.dumps(cert))
                removed = partial['parts'][0]['rows'].pop(0)
                missing = {tuple(removed['key'])}
                actual_hole = check(req, partial, budget.tick)
                expected_hole = least_hole(oracle, partial['parts'][0]['support'], missing)
                assert actual_hole['status'] == 'UNCOVERED' and actual_hole['witness'] == expected_hole
                record['hole'] = actual_hole
            report['variants'].append(record)
        assert report['variants'][3]['unsafe_value_only_accepts'] is True
        assert report['variants'][1]['semantic_only_diagnostic'] != report['variants'][1]['witness']
        report['outcome'] = 'PASS_FINITE_PILOT'
    except Exception as e:
        report['error'] = type(e).__name__ + ': ' + str(e)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        report['resources'] = budget.report()
        (ROOT / 'results' / 'pilot.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
