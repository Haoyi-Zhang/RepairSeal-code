"""Run the frozen, finite intake study. No network or submitted native C runs."""
from __future__ import annotations
import argparse
import copy
import csv
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from budget import Budget, enforce_limits
from checker import Session, check
from producer import Producer
from fixture_oracle import (NAMES, VARIANTS, CORES, request, exhaustive,
                            least_violation, least_hole)


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n')


def corruptions(cert):
    """Exactly eight prospective malformed-evidence controls."""
    names = ('flipped-assertion', 'duplicate-cell', 'missing-obligation',
             'wrong-obligation', 'foreign-support', 'boolean-key',
             'insufficient-support', 'extra-field')
    for name in names:
        c = copy.deepcopy(cert)
        if name == 'flipped-assertion':
            c['parts'][0]['rows'][0]['ok'] = not c['parts'][0]['rows'][0]['ok']
        elif name == 'duplicate-cell':
            c['parts'][0]['rows'].append(copy.deepcopy(c['parts'][0]['rows'][0]))
        elif name == 'missing-obligation': c['parts'].pop()
        elif name == 'wrong-obligation': c['parts'][0]['obligation'] = 'untrusted-defined'
        elif name == 'foreign-support': c['parts'][0]['support'].append('foreign')
        elif name == 'boolean-key':
            part = next(p for p in c['parts'] if p['support'])
            part['rows'][0]['key'][0] = False
        elif name == 'insufficient-support':
            part = next(p for p in c['parts'] if p['support'])
            part['support'].pop(0)
            for row in part['rows']: row['key'].pop(0)
        elif name == 'extra-field': c['repair_guard'] = 'x != x'
        yield name, c


def factorization(rows, names, truths, budget):
    seen = {}; indices = [NAMES.index(n) for n in names]
    for row, truth in zip(rows, truths):
        budget.tick('support_comparisons')
        key = tuple(row['input'][i] for i in indices)
        if key in seen:
            assert seen[key] == truth, ('nonconstant support fiber', names, key)
        else: seen[key] = truth
    return len(seen)


def native_cross_check(records, out, budget):
    """Cross-check all known-defined fixture values with real GCC and Clang runs."""
    functions = {}; evaluations = {}; excluded = 0
    for req, rows in records:
        for role in ('original', 'candidate', 'reference'):
            source = req[role]
            if source not in functions: functions[source] = len(functions)
            for row in rows:
                value = row[role]
                if value is None:
                    excluded += 1
                    continue
                key = (functions[source], tuple(row['input']))
                if key in evaluations: assert evaluations[key] == value
                else: evaluations[key] = value
    budget.tick('native_defined_evaluations', len(evaluations))
    compiler_specs = []
    for compiler_id in ('gcc', 'clang'):
        executable = shutil.which(compiler_id)
        if executable is None:
            raise RuntimeError('native C cross-check requires both GCC and Clang')
        compiler_specs.append((compiler_id, str(Path(executable).resolve())))
    declarations = [s.replace('unsigned f(', 'unsigned f' + str(i) + '(', 1)
                    for s, i in functions.items()]
    names = ', '.join('f' + str(i) for i in range(len(functions)))
    cases = ',\n'.join('{' + ','.join(str(n)+'u' for n in (fid, *point)) + '}'
                       for fid, point in evaluations)
    harness = ('#include <stdio.h>\n#include <limits.h>\n'
               '_Static_assert(UINT_MAX == 4294967295u, "requires unsigned32");\n' +
               '\n'.join(declarations) + '\n'
               'typedef unsigned (*fun)(unsigned,unsigned,unsigned,unsigned);\n'
               'static fun functions[] = {' + names + '};\n'
               'static const unsigned cases[][5] = {\n' + cases + '\n};\n'
               'int main(void) {\n'
               ' for (unsigned k=0; k<sizeof(cases)/sizeof(cases[0]); ++k) {\n'
               '  const unsigned *p=cases[k];\n'
               '  printf("%u\\n",functions[p[0]](p[1],p[2],p[3],p[4]));\n'
               ' } return 0;\n}\n')
    source_path = out / 'native-harness.c'; source_path.write_text(harness)
    expected_values = list(evaluations.values())
    identities = []
    observed_by_compiler = {}
    for compiler_id, executable in compiler_specs:
        version_command = [executable, '--version']
        version = subprocess.run(version_command, capture_output=True, text=True,
                                 timeout=15, check=False)
        if version.returncode != 0:
            raise AssertionError(version.stderr)
        binary_name = 'native-' + compiler_id
        compile_command = [executable, '-std=c11', '-O0', 'native-harness.c', '-o', binary_name]
        run_command = ['./' + binary_name]
        compiled = subprocess.run(compile_command, cwd=out, capture_output=True,
                                  text=True, timeout=45, check=False)
        if compiled.returncode != 0:
            raise AssertionError(compiler_id + ': ' + compiled.stderr)
        run = subprocess.run(run_command, cwd=out, capture_output=True, text=True,
                             timeout=30, check=False)
        (out / binary_name).unlink(missing_ok=True)
        if run.returncode != 0:
            raise AssertionError(compiler_id + ': ' + run.stderr)
        observed = [int(line) for line in run.stdout.splitlines()]
        if observed != expected_values:
            raise AssertionError(compiler_id + ': native C return-value mismatch')
        observed_by_compiler[compiler_id] = observed
        output_name = 'native-outputs-' + compiler_id + '.csv'
        with (out / output_name).open('w', newline='') as f:
            writer = csv.writer(f); writer.writerow(['function', *NAMES, 'expected', 'observed'])
            for ((fid, point), expected), actual in zip(evaluations.items(), observed):
                writer.writerow([fid, *point, expected, actual])
        identities.append({
            'id': compiler_id,
            'executable': executable,
            'version_command': version_command,
            'version_first_line': version.stdout.splitlines()[0],
            'compile_command': compile_command,
            'run_command': run_command,
            'output_file': output_name,
            'compile_returncode': compiled.returncode,
            'run_returncode': run.returncode,
        })
    if observed_by_compiler['gcc'] != observed_by_compiler['clang']:
        raise AssertionError('GCC/Clang native output disagreement')
    compiler_record = {
        'schema': 'native-compiler-cross-check-v1',
        'harness': 'native-harness.c',
        'compilers': identities,
        'rows_per_compiler': len(evaluations),
        'cross_compiler_disagreements': 0,
    }
    save(out / 'native-compilers.json', compiler_record)
    return {'unique_functions': len(functions), 'unique_defined_evaluations': len(evaluations),
            'undefined_candidate_observations_excluded': excluded,
            'return_value_disagreements': 0, 'cross_compiler_disagreements': 0,
            'trace_checked_natively': False, 'compiler_count': 2,
            'compilers': identities, 'compile_options': ['-std=c11', '-O0']}


def study(out, budget):
    for d in ('certificates', 'controls', 'oracle'): (out / d).mkdir(parents=True, exist_ok=True)
    inputs = ROOT / 'inputs'; inputs.mkdir(exist_ok=True)
    reports = []; records = []; holes = []; tampering = []
    for case in range(1, 21):
        for variant in VARIANTS:
            req = request(case, variant); rows = exhaustive(case, variant)
            budget.tick('requests'); budget.tick('obligation_families', 3); budget.tick('oracle_rows', len(rows))
            if variant != 'correct': budget.tick('source_mutations')
            records.append((req, rows)); input_path = inputs / (req['id'] + '.json')
            if input_path.exists():
                assert json.loads(input_path.read_text()) == req, ('retained input differs', req['id'])
            else: save(input_path, req)
            save(out / 'oracle' / (req['id'] + '.json'), rows)
            producer = Producer(req, budget.tick); cert = producer.certificate()
            save(out / 'certificates' / (req['id'] + '.json'), cert)
            session = Session(req, budget.tick); actual = session.check(cert)
            exact = least_violation(rows)
            assert actual['status'] == ('ACCEPT' if exact is None else 'REFUTED'), (req['id'], actual)
            assert actual['witness'] == exact, (req['id'], actual, exact)
            for row in rows:
                env = dict(zip(NAMES, row['input']))
                assert [session.predicate(j, env) for j in range(3)] == row['truth'], req['id']
                for role in ('original', 'candidate', 'reference'):
                    result = session.run(role, env)
                    assert result[0] == (row[role] is not None)
                    if result[0]: assert result[1] == row[role], (req['id'], role, row)
                assert [list(p) for p in session.run('candidate', env)[2]] == row['trace'], req['id']
            for j in range(3):
                factorization(rows, session.required[j], [r['truth'][j] for r in rows], budget)
                factorization(rows, producer.support(j), [r['truth'][j] for r in rows], budget)
            factorization(rows, session.trace_variables, [r['trace'] for r in rows], budget)
            q = producer.programs['candidate']; trace_support = set()
            for _, reach, guard in q.trace_events:
                trace_support.update(producer.dag.fvs[reach]); trace_support.update(producer.dag.fvs[guard])
            factorization(rows, trace_support, [r['trace'] for r in rows], budget)
            report = {'id': req['id'], 'family': CORES[case - 1][0], 'variant': variant,
                      'status': actual['status'], 'witness': actual['witness'],
                      'oracle_points': len(rows), 'projected_rows': sum(len(p['rows']) for p in cert['parts']),
                      'producer_dag_nodes': len(producer.dag.nodes), 'checker_symbolic_nodes': session.symbols,
                      'supports': [p['support'] for p in cert['parts']],
                      'checker_trace_support': [n for n in NAMES if n in session.trace_variables],
                      'test_only_accepts': all(rows[0]['truth'])}
            if exact is not None:
                j = ('defined', 'repair', 'preserve').index(exact['obligation'])
                report['semantic_only_witness'] = producer.diagnostic(j, semantic_only=True)
                report['trace_aware_witness'] = producer.diagnostic(j)
                assert report['trace_aware_witness'] == exact, req['id']
                report['semantic_only_is_canonical'] = report['semantic_only_witness'] == exact
            if variant == 'undefined':
                report['unsafe_value_only_accepts'] = producer.unsafe_value_only_accepts()
                assert report['unsafe_value_only_accepts'] is True, req['id']
            if variant == 'correct':
                unsliced = producer.certificate(unsliced=True)
                baseline = check(req, unsliced, budget.tick)
                assert baseline['status'] == 'ACCEPT'
                report['unsliced_rows'] = sum(len(p['rows']) for p in unsliced['parts'])
                save(out / 'certificates' / (req['id'] + '-unsliced.json'), unsliced)
                partial = copy.deepcopy(cert); missing_row = partial['parts'][0]['rows'].pop(0)
                missing = {tuple(missing_row['key'])}
                result = check(req, partial, budget.tick)
                expected = least_hole(rows, partial['parts'][0]['support'], missing)
                assert result['status'] == 'UNCOVERED' and result['witness'] == expected, req['id']
                budget.tick('certificate_mutations')
                save(out / 'controls' / (req['id'] + '-hole.json'), partial)
                holes.append({'id': req['id'], **result})
                for name, damaged in corruptions(cert):
                    budget.tick('certificate_mutations')
                    result = check(req, damaged, budget.tick)
                    assert result['status'] == 'INVALID', (req['id'], name, result)
                    save(out / 'controls' / (req['id'] + '-' + name + '.json'), damaged)
                    tampering.append({'id': req['id'], 'mutation': name, **result})
            reports.append(report)
    native = native_cross_check(records, out, budget)
    totals = {'fixture_families': 20, 'requests': len(reports), 'oracle_points': 6480,
              'accepted_correct': sum(r['status'] == 'ACCEPT' for r in reports),
              'refuted_mutants': sum(r['status'] == 'REFUTED' for r in reports),
              'test_only_accepted_mutants': sum(r['test_only_accepts'] for r in reports if r['variant'] != 'correct'),
              'unsafe_value_only_accepted_undefined': sum(r.get('unsafe_value_only_accepts', False) for r in reports),
              'semantic_only_noncanonical_refutations': sum(not r['semantic_only_is_canonical'] for r in reports if 'semantic_only_is_canonical' in r),
              'trace_aware_exact_refutations': sum(r.get('trace_aware_witness') == r['witness'] for r in reports if r['status'] == 'REFUTED'),
              'correct_patch_coverage_holes': len(holes), 'invalid_certificate_controls': len(tampering),
              'public_codeflaws_pairs': 0, 'oracle_disagreements': 0}
    save(out / 'cases.json', reports); save(out / 'holes.json', holes); save(out / 'tampering.json', tampering)
    with (out / 'case-summary.csv').open('w', newline='') as f:
        columns = ['id','variant','status','oracle_points','projected_rows','producer_dag_nodes',
                   'checker_symbolic_nodes','test_only_accepts','unsliced_rows','semantic_only_is_canonical',
                   'unsafe_value_only_accepts']
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore'); writer.writeheader(); writer.writerows(reports)
    return {'outcome': 'PASS_FINITE_STUDY', 'totals': totals, 'native': native,
            'scope': 'designed finite intake fixtures; not a public benchmark or general correctness proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'results')
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    enforce_limits(); budget = Budget(operation_limit=1_150_000)
    result = {'outcome': 'FAILED'}
    try: result = study(out, budget)
    except Exception as e:
        result['error'] = type(e).__name__ + ': ' + str(e); result['traceback'] = traceback.format_exc()
        raise
    finally:
        result['resources'] = budget.report(); save(out / 'study.json', result)
        print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
