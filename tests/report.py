"""Derive publication tables from retained exact observations, without new inputs."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from budget import Budget, enforce_limits

def read(path):
    return json.loads(path.read_text())

def table(columns, rows, alignment):
    out = ['\\begin{tabular}{' + alignment + '}', '\\toprule', ' & '.join(columns) + r' \\', '\\midrule']
    out += [' & '.join(str(v) for v in row) + r' \\' for row in rows]
    return '\n'.join(out + ['\\bottomrule', '\\end{tabular}']) + '\n'

def build(results, output, budget):
    cases = read(results / 'cases.json')
    study = read(results / 'study.json')
    null = read(results / 'null-control.json')
    regression = read(results / 'regression.json')
    holes = read(results / 'holes.json')
    tampering = read(results / 'tampering.json')
    good = [c for c in cases if c['variant'] == 'correct']
    bad = [c for c in cases if c['variant'] != 'correct']
    assert len(cases) == 80 and len(good) == 20 and len(bad) == 60
    oracle_points = 0
    for c in cases:
        budget.tick('report_cases')
        oracle = read(results / 'oracle' / (c['id'] + '.json'))
        budget.tick('report_oracle_observations', len(oracle))
        oracle_points += len(oracle)
        assert len(oracle) == c['oracle_points']
        expected = None
        for j, label in enumerate(('defined', 'repair', 'preserve')):
            failing = [r for r in oracle if not r['truth'][j]]
            if failing:
                r = min(failing, key=lambda row: (row['trace'], row['input']))
                expected = {'obligation': label, 'trace': r['trace'], 'input': r['input']}
                break
        assert c['witness'] == expected
        assert c['status'] == ('ACCEPT' if expected is None else 'REFUTED')
    native_by_compiler = {
        compiler: list(csv.DictReader((results / ('native-outputs-' + compiler + '.csv')).open()))
        for compiler in ('gcc', 'clang')
    }
    for compiler, rows in native_by_compiler.items():
        budget.tick('report_native_rows', len(rows))
        assert all(r['expected'] == r['observed'] for r in rows), compiler
        assert len(rows) == study['native']['unique_defined_evaluations']
    assert native_by_compiler['gcc'] == native_by_compiler['clang']
    native = native_by_compiler['gcc']
    for r in null['records']:
        budget.tick('report_null_rows')
        c = next(c for c in cases if c['id'] == r['id'])
        assert (r['status'], r['witness']) == (c['status'], c['witness'])
        assert r['certificate_rows'] == r['direct_rows']
    m = {
        'families': len(good), 'requests': len(cases), 'oracle_points': oracle_points,
        'accepted_correct': sum(c['status'] == 'ACCEPT' for c in good),
        'refuted_mutants': sum(c['status'] == 'REFUTED' for c in bad),
        'test_only_accepted_mutants': sum(c['test_only_accepts'] for c in bad),
        'value_only_accepted_undefined': sum(c.get('unsafe_value_only_accepts', False) for c in bad),
        'semantic_only_noncanonical': sum(c.get('semantic_only_is_canonical') is False for c in bad),
        'trace_aware_exact': sum(c.get('trace_aware_witness') == c['witness'] for c in bad),
        'holes': len(holes), 'tamperings': len(tampering), 'native_defined': len(native),
        'native_excluded_undefined': study['native']['undefined_candidate_observations_excluded'],
        'projected_rows_correct': sum(c['projected_rows'] for c in good),
        'unsliced_rows_correct': sum(c['unsliced_rows'] for c in good),
        'all_projected_rows': sum(c['projected_rows'] for c in cases),
        'rows_range': [min(c['projected_rows'] for c in cases), max(c['projected_rows'] for c in cases)],
        'producer_nodes_range': [min(c['producer_dag_nodes'] for c in cases), max(c['producer_dag_nodes'] for c in cases)],
        'receiver_nodes_range': [min(c['checker_symbolic_nodes'] for c in cases), max(c['checker_symbolic_nodes'] for c in cases)],
        'public_pairs': study['totals']['public_codeflaws_pairs'],
        'regression': regression['totals'], 'null': null['totals'],
        'null_counts': null['aggregate_counts'],
    }
    assert all(r['status'] == 'UNCOVERED' for r in holes)
    assert all(r['status'] == 'INVALID' for r in tampering)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'summary.json').write_text(json.dumps(m, indent=2) + '\n')
    rows = [(str(i+1), c['family'], c['projected_rows'], c['producer_dag_nodes'], c['checker_symbolic_nodes']) for i,c in enumerate(good)]
    (output / 'families.tex').write_text(table(['Case', 'Arithmetic/control core', 'Rows', 'P nodes', 'C nodes'], rows, 'r l r r r'))
    rows = [('Correct candidates accepted', m['accepted_correct'], 20),
            ('Source mutants refuted', m['refuted_mutants'], 60),
            ('Weak test control accepts invalid mutants', m['test_only_accepted_mutants'], 60),
            ('Value-only control misses undefined operation', m['value_only_accepted_undefined'], 20),
            ('Semantic-only diagnostic is not least', m['semantic_only_noncanonical'], 60),
            ('Trace-aware diagnostic equals full oracle', m['trace_aware_exact'], 60),
            ('Missing-cell control returns UNCOVERED', m['holes'], 20),
            ('Corrupted-certificate control returns INVALID', m['tamperings'], 160)]
    (output / 'outcomes.tex').write_text(table(['Finite observation', 'Count', 'Cases'], rows, 'l r r'))
    names = [('Predicate replay rows', 'rows'), ('Projected inputs, including diagnostics', 'checker_projected_points'),
             ('Source-interpreter steps', 'checker_steps'), ('Source token admissions', 'checker_source_tokens'),
             ('Dependency-algebra nodes', 'checker_symbolic_nodes'), ('Counterexample comparisons', 'counterexample_comparisons'),
             ('Certificate rows processed', 'certificate_steps'), ('Coverage cells processed', 'coverage_cells')]
    sums = null['aggregate_counts']
    rows = [(label, null['totals']['certificate_rows'] if key == 'rows' else sums['certificate_arm'][key],
             null['totals']['direct_rows'] if key == 'rows' else sums['receiver_only_arm'][key]) for label,key in names]
    (output / 'null.tex').write_text(table(['Work item (all 80 requests)', 'Certificate', 'No certificate'], rows, 'l r r'))
    return {'outcome': 'PASS_DATA_RECONCILIATION', 'summary': m}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, default=ROOT / 'results')
    p.add_argument('--output', type=Path, default=ROOT / 'results' / 'publication')
    a = p.parse_args(); enforce_limits(); budget = Budget(25_000)
    result = build(a.results, a.output, budget)
    result['resources'] = budget.report()
    (a.output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'outcome': result['outcome'], 'resources': result['resources']}, indent=2))
if __name__ == '__main__':
    main()
