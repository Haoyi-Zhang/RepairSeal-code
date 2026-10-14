"""Optional natural-source admission and whole-program correspondence study.

Default model replay is offline. --archive inspects an externally obtained,
fixed dataset without running its scripts. --execute-reviewed additionally
compiles only four complete C files with exact reviewed fingerprints. Downloaded
sources, test payloads, compiler and executables remain in the supplied private
output directory; only derived records are suitable for artifact publication.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,re,subprocess,sys,tarfile,threading,time
from collections import Counter
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from proof_dag_checker import (Reader,Unsupported,Invalid,build_expected,validate_request_fields,
    exact_equal,load_json_strict,evaluate_topological,check,OBLIGATIONS)
from proof_dag_producer import produce,canonical_bytes
from refutation_witness_producer import produce as package_point
from refutation_witness_checker import check as check_point,_evaluate_point,_trace
from codeflaws_cases import CASES,request,value,trace,legal_input,decode_output
ARCHIVE_SHA='2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11'
ARCHIVE_BYTES=265695532
TIMING_STAGES=('request_construct_ms','request_encode_ms','request_decode_ms','producer_ms',
    'packet_encode_ms','receiver_request_decode_ms','packet_decode_ms','receiver_ms','result_encode_ms','total_ms')

def fingerprint(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(1024*1024):h.update(data)
    return h.hexdigest()

def write_json(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def point_direct(q,w,count=None):
    domains,names=validate_request_fields(q)
    if type(w)is not dict or set(w)!={'obligation','trace','input'}:raise Invalid('point claim schema')
    o,p,t=w['obligation'],w['input'],w['trace']
    if type(o)is not str or o not in OBLIGATIONS:raise Invalid('point obligation')
    if type(p)is not list or len(p)!=len(names) or any(type(x)is not int for x in p):raise Invalid('point input')
    if any(x not in domains[n] for n,x in zip(names,p)):raise Invalid('point membership')
    if type(t)is not list or any(type(e)is not list or len(e)!=2 or type(e[0])is not int or type(e[1])is not int or e[0]<0 or e[1] not in (0,1) for e in t):raise Invalid('point trace')
    c,progs,_g,roots=build_expected(q);vs=_evaluate_point(c,names,p,count or (lambda *a:None))
    if vs[roots[OBLIGATIONS.index(o)]] is not False or not exact_equal(t,_trace(progs['candidate'].events,vs)):raise Invalid('point claim false')
    return {'status':'REFUTED','witness':w,'checked_cells':len(c.nodes),'checked_nodes':len(c.nodes)}

def oracle(case,role):
    c=CASES[case];bad=[]
    for x in c['domain']:
        q,p,r=(value(case,k,x) for k in (role,'buggy','reference'))
        region=(x==2) if case=='4-A' else True
        for j,holds in enumerate((True,not region or q==r,region or q==p)):
            if not holds:bad.append((j,trace(case,role,x),[x]))
    if not bad:return {'status':'ACCEPT','witness':None}
    j,t,p=min(bad)
    return {'status':'REFUTED','witness':{'obligation':OBLIGATIONS[j],'trace':t,'input':p}}

def result_core(r):return {k:r[k] for k in ('status','witness')}

def serialize_run(case,role,method):
    if method not in {'full','direct'}:raise ValueError('timing method')
    stages={};start=time.perf_counter_ns()
    def timed(name,fn):
        t=time.perf_counter_ns();v=fn();stages[name]=(time.perf_counter_ns()-t)/1e6;return v
    q=timed('request_construct_ms',lambda:request(case,role))
    qwire=timed('request_encode_ms',lambda:json.dumps(q,separators=(',',':')).encode())
    q=timed('request_decode_ms',lambda:load_json_strict(qwire.decode()))
    if method=='full':
        packet=timed('producer_ms',lambda:produce(q))
        wire=timed('packet_encode_ms',lambda:canonical_bytes(packet))
        q=timed('receiver_request_decode_ms',lambda:load_json_strict(qwire.decode()))
        packet=timed('packet_decode_ms',lambda:load_json_strict(wire.decode()))
        result=timed('receiver_ms',lambda:check(q,packet))
    else:result=timed('receiver_ms',lambda:evaluate_topological(q))
    timed('result_encode_ms',lambda:json.dumps(result).encode())
    stages['total_ms']=(time.perf_counter_ns()-start)/1e6
    return result,stages

def replay_models(out,repetitions):
    outcomes=[];timings=[];requests=[]
    for case in CASES:
        for role in ('buggy','supplied'):
            q=request(case,role);requests.append(q)
            count=Counter();full_count=Counter();direct_count=Counter()
            cert=produce(q,lambda k,n=1:count.update({k:n}))
            a=check(q,cert,lambda k,n=1:full_count.update({k:n}))
            b=evaluate_topological(q,lambda k,n=1:direct_count.update({k:n}));expected=oracle(case,role)
            if not (result_core(a)==result_core(b)==expected):raise RuntimeError('natural model/oracle disagreement')
            if a['checked_cells']!=b['checked_cells'] or count['producer_vector_cells']!=a['checked_cells']:raise RuntimeError('unequal full-domain semantic work')
            if full_count['proof_cells']!=a['checked_cells'] or direct_count['topological_cells']!=b['checked_cells']:raise RuntimeError('receiver callback count mismatch')
            compact=None
            if a['status']=='REFUTED':
                compact_count=Counter();point_count=Counter();cp=package_point(q,a['witness'])
                cr=check_point(q,cp,lambda k,n=1:compact_count.update({k:n}))
                dr=point_direct(q,a['witness'],lambda k,n=1:point_count.update({k:n}))
                if not (result_core(cr)==result_core(dr)==expected) or cr['checked_cells']!=dr['checked_cells']:raise RuntimeError('same-point comparison')
                if compact_count['refutation_cells']!=cr['checked_cells'] or point_count['refutation_cells']!=dr['checked_cells']:raise RuntimeError('point callback count mismatch')
                compact={'canonical_bytes':len(canonical_bytes(cp)),'cells':cr['checked_cells'],'status':cr['status'],
                    'operation_counts':{'compact':dict(compact_count),'point_direct':dict(point_count)},
                    'discovery':'already computed full-domain direct classification; discovery not charged as zero'}
            outcomes.append({'case':case,'candidate_origin':role,'points':64,'full_cells':a['checked_cells'],'direct_cells':b['checked_cells'],'nodes':a['checked_nodes'],'full_bytes':len(canonical_bytes(cert)),**expected,'compact':compact,
                'operation_counts':{'producer':dict(count),'full':dict(full_count),'direct':dict(direct_count)}})
            for warmup in range(2):
                for method in (('full','direct') if warmup%2==0 else ('direct','full')):
                    api=check(q,cert) if method=='full' else evaluate_topological(q)
                    serialized,_stages=serialize_run(case,role,method)
                    if result_core(api)!=expected or result_core(serialized)!=expected:raise RuntimeError('warmup result disagreement')
            for rep in range(repetitions):
                order=('full','direct') if rep%2==0 else ('direct','full')
                for rank,method in enumerate(order):
                    t=time.perf_counter_ns();api=check(q,cert) if method=='full' else evaluate_topological(q)
                    api_ms=(time.perf_counter_ns()-t)/1e6
                    r,stages=serialize_run(case,role,method)
                    if result_core(api)!=expected or result_core(r)!=expected:raise RuntimeError('timed result disagreement')
                    timings.append({'case':case,'candidate_origin':role,'repetition':rep,'rank':rank,'method':method,'api_ms':api_ms,**{k:stages.get(k,'') for k in TIMING_STAGES}})
    write_json(out/'requests.json',requests);write_json(out/'model-outcomes.json',outcomes);write_csv(out/'timing.csv',timings)
    return outcomes,timings

def inspect(archive,out):
    if archive.stat().st_size!=ARCHIVE_BYTES or fingerprint(archive)!=ARCHIVE_SHA:raise ValueError('not the fixed reviewed official archive')
    subjects=[x.split('\t')[0] for x in (ROOT/'public-data/codeflaws-first-300.tsv').read_text().splitlines()]
    rows=[];chosen={};tests={c:{'repair':[],'heldout':[]} for c in CASES};seen=set()
    with tarfile.open(archive,'r|gz') as tar:
        for m in tar:
            parts=PurePosixPath(m.name).parts
            if len(parts)!=3 or parts[0]!='codeflaws' or '..' in parts:continue
            subject,name=parts[1:]
            # Freeze input filenames from metadata, including invalid/non-file slots.
            # Payload size, type, pairing and contents must not select replacements.
            for case,c in CASES.items():
                if subject==c['subject'] and re.fullmatch(r'(?:heldout-)?input[^/]*',name):
                    tests[case]['heldout' if name.startswith('heldout-') else 'repair'].append(m.name)
            if subject in subjects and re.fullmatch(r'[0-9]+-[A-Za-z0-9]+-[0-9]+\.c',name):
                if not m.isfile() or not 0<=m.size<=65536:raise ValueError('source member outside reviewed bounds')
                identity=(subject,name)
                if identity in seen:raise ValueError('duplicate source member')
                seen.add(identity);data=tar.extractfile(m).read()
                try:source=data.decode('utf-8',errors='strict');Reader(source).program();status='admitted';reason=''
                except (UnicodeDecodeError,Unsupported,Invalid) as exc:status='rejected';reason='source encoding' if isinstance(exc,UnicodeDecodeError) else str(exc)
                rows.append({'subject':subject,'member':m.name,'source_bytes':len(data),'source_sha256':hashlib.sha256(data).hexdigest(),'receiver_admission':status,'reason':reason})
                for case,c in CASES.items():
                    if c['subject']==subject:
                        for role,(filename,digest) in c['sources'].items():
                            if name==filename:
                                if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('reviewed C source differs')
                                chosen[(case,role)]=data
    if len(rows)!=600 or len(seen)!=600 or len(chosen)!=4:raise ValueError('incomplete natural source cohort')
    for d in tests.values():
        for split in d:d[split]=sorted(set(d[split]))[:8]
    write_json(out/'source-admission.json',{'indexed_pairs':300,'source_member_occurrences':600,'distinct_submission_filenames':len({x['member'].split('/')[-1] for x in rows}),'distinct_source_contents':len({x['source_sha256'] for x in rows}),'admitted_original_sources':sum(x['receiver_admission']=='admitted' for x in rows),'rows':rows,'rejection_semantics':'unsupported source syntax, not a verdict about repair correctness'})
    write_json(out/'test-selection.json',tests)
    return chosen,tests

def pin_affinity():
    if os.name=='nt':
        import ctypes
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.GetCurrentProcess.restype=ctypes.c_void_p
        k.GetProcessAffinityMask.argtypes=(ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t))
        k.SetProcessAffinityMask.argtypes=(ctypes.c_void_p,ctypes.c_size_t)
        process=k.GetCurrentProcess()
        pm=ctypes.c_size_t();sm=ctypes.c_size_t()
        if not k.GetProcessAffinityMask(process,ctypes.byref(pm),ctypes.byref(sm)):raise OSError('affinity query failed')
        bits=[1<<i for i in range(64) if pm.value&(1<<i)]
        if not k.SetProcessAffinityMask(process,sum(bits[:2])):raise OSError('affinity failed')

def native_input(case,raw):
    if type(raw)is not bytes or not 0<len(raw)<=256 or not re.fullmatch(rb'\s*[0-9]+\s*',raw):
        raise ValueError('selected test outside fixed single-integer input contract')
    x=int(raw)
    if not legal_input(case,x):raise ValueError('selected test outside fixed legal task inputs')
    return x


def test_output_member(member):
    path=PurePosixPath(member);name=path.name
    prefix='heldout-input' if name.startswith('heldout-input') else 'input'
    return str(path.with_name(prefix.replace('input','output')+name[len(prefix):]))


def read_selected_tests(archive,tests):
    """Read frozen slots only; invalid/unavailable slots never select replacements."""
    selected={p for by_split in tests.values() for paths in by_split.values() for p in paths}
    needed=selected|{test_output_member(p) for p in selected};payload={}
    with tarfile.open(archive,'r|gz') as tar:
        for m in tar:
            if m.name not in needed:continue
            if m.name in payload:
                payload[m.name]={'status':'invalid','reason':'duplicate selected member'}
            elif not m.isfile() or not 0<=m.size<=256:
                payload[m.name]={'status':'invalid','reason':'selected member type/size outside contract'}
            else:
                data=tar.extractfile(m).read(257)
                payload[m.name]=({'status':'valid','data':data} if len(data)==m.size else
                    {'status':'invalid','reason':'selected member size mismatch'})
    rows=[];valid=[]
    for case,by_split in tests.items():
        for split,paths in by_split.items():
            if not paths:
                rows.append({'case':case,'split':split,'slot':None,'test_member':None,
                    'selection_status':'unavailable','reason':'no input filenames available'})
            for slot,member in enumerate(paths,1):
                key=test_output_member(member)
                row={'case':case,'split':split,'slot':slot,'test_member':member,'output_member':key}
                entries=[payload.get(p,{'status':'unavailable','reason':'missing selected member'}) for p in (member,key)]
                row.update(input_status=entries[0]['status'],output_status=entries[1]['status'])
                problems=[e for e in entries if e['status']!='valid']
                if problems:
                    row.update(selection_status='invalid' if any(e['status']=='invalid' for e in problems) else 'unavailable',
                        reason='; '.join(e['reason'] for e in problems))
                else:
                    raw,expected=(e['data'] for e in entries)
                    row.update(input_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest())
                    reasons=[]
                    try:native_input(case,raw)
                    except ValueError as exc:row['input_status']='invalid';reasons.append('input: '+str(exc))
                    try:target=decode_output(case,expected)
                    except (ValueError,UnicodeError) as exc:row['output_status']='invalid';reasons.append('output: '+str(exc))
                    if reasons:row.update(selection_status='invalid',reason='; '.join(reasons))
                    else:
                        row.update(selection_status='valid',reason='')
                        valid.append((row,raw,target))
                rows.append(row)
    return rows,valid


class ReviewedNativeRunner:
    """Trusted compiler queries and four fingerprinted sources, not an arbitrary runner.

    Pipe readers retain bounded prefixes and kill on overflow. Raw bytes and process
    outcomes are persisted before any observation decoding. No environment is logged.
    """
    def __init__(self,out,compiler,zig):
        self.work=out.resolve()/'private-native';self.work.mkdir()
        compiler=compiler.resolve()
        if not compiler.is_file():raise ValueError('local compiler required')
        self.front=[str(compiler)]+(['cc'] if zig else [])
        self.env=dict(os.environ)
        self.env['ZIG_GLOBAL_CACHE_DIR']=str(self.work/'zig-cache')
        self.env['ZIG_LOCAL_CACHE_DIR']=str(self.work/'zig-local')
        self.records=[];self.binaries={}

    def persist(self):write_json(self.work/'subprocess-records.json',self.records)

    def _run(self,label,command,raw,timeout,stdout_limit=65536,stderr_limit=65536):
        # Only diagnostic/compile_reviewed/observe construct commands for this method.
        index=len(self.records)+1;started=time.perf_counter();process=None;threads=[]
        buffers={'stdout':bytearray(),'stderr':bytearray()};seen={'stdout':0,'stderr':0}
        limits={'stdout':stdout_limit,'stderr':stderr_limit};overflow=threading.Event()
        errors=[];lock=threading.Lock()
        record={'index':index,'stage':label,'command':command,'cwd':str(self.work),
            'input_bytes':len(raw),'input_sha256':hashlib.sha256(raw).hexdigest(),
            'timeout_seconds':timeout,'returncode':None,'outcome':'spawn_error'}

        def stop():
            try:process.kill()
            except OSError:pass

        def drain(name,pipe):
            try:
                while chunk:=pipe.read(4096):
                    with lock:
                        seen[name]+=len(chunk)
                        buffers[name].extend(chunk[:max(0,limits[name]-len(buffers[name]))])
                        exceeded=seen[name]>limits[name]
                    if exceeded:overflow.set();stop()
            except OSError as exc:
                with lock:errors.append(str(exc))
                stop()
            finally:pipe.close()

        try:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                cwd=self.work,env=self.env,shell=False)
            for name in buffers:
                thread=threading.Thread(target=drain,args=(name,getattr(process,name)),daemon=True)
                thread.start();threads.append(thread)
            try:
                process.stdin.write(raw)
            except (BrokenPipeError,OSError) as exc:
                record['input_error']=str(exc)
            finally:
                try:process.stdin.close()
                except (BrokenPipeError,OSError) as exc:record['input_error']=str(exc)
            try:
                process.wait(timeout=timeout)
                record['outcome']='ok' if process.returncode==0 else 'nonzero'
            except subprocess.TimeoutExpired:
                record['outcome']='timeout';stop();process.wait()
        except OSError as exc:
            record['error']=str(exc)
        finally:
            if process is not None:
                if process.poll() is None:stop();process.wait()
                record['returncode']=process.returncode
            for thread in threads:thread.join(timeout=1)
            if record['outcome'] not in {'timeout','spawn_error'}:
                if overflow.is_set():record['outcome']='output_limit'
                elif errors or any(t.is_alive() for t in threads):record['outcome']='capture_error'
                elif 'input_error' in record:record['outcome']='input_error'
            if errors:record['capture_errors']=errors
            record['capture_incomplete']=any(t.is_alive() for t in threads)
            with lock:
                captured={name:bytes(data) for name,data in buffers.items()}
                for name in buffers:
                    path=self.work/(f'process-{index:05d}.{name}.bin');path.write_bytes(captured[name])
                    record[name+'_path']=str(path.relative_to(self.work.parent))
                    record[name+'_bytes_seen']=seen[name]
                    record[name+'_limit']=limits[name]
                    record[name+'_truncated']=seen[name]>limits[name]
            record['elapsed_seconds']=time.perf_counter()-started
            record['process_outcome']=record['outcome']
            self.records.append(record);self.persist()
        return record,captured['stdout'],captured['stderr']

    def diagnostic(self,name):
        commands={'version':(['--version'],b'',20),'macros':(['-dM','-E','-x','c','-'],b'#include <limits.h>\n',60)}
        args,raw,timeout=commands[name]
        return self._run(name,self.front+args,raw,timeout)

    def compile_reviewed(self,case,role,data):
        if case not in CASES or role not in CASES[case]['sources']:raise ValueError('unreviewed source role')
        if type(data)is not bytes or hashlib.sha256(data).hexdigest()!=CASES[case]['sources'][role][1]:
            raise ValueError('reviewed C source differs')
        source=self.work/(case+'-'+role+'.c');source.write_bytes(data)
        executable=self.work/(case+'-'+role+('.exe' if os.name=='nt' else ''))
        result=self._run('compile',self.front+['-std=c11','-O0',str(source),'-o',str(executable)],b'',300)
        result[0].update(case=case,role=role,source_sha256=CASES[case]['sources'][role][1]);self.persist()
        if result[0]['outcome']=='ok':self.binaries[(case,role)]=executable
        return result

    def observe(self,case,role,raw):
        native_input(case,raw)
        executable=self.binaries[(case,role)]  # Only successful reviewed compilation registers a binary.
        record,stdout,stderr=self._run('observe',[str(executable)],raw,5,128,4096)
        record.update(case=case,role=role,source_sha256=CASES[case]['sources'][role][1])
        record['process_outcome']=record['outcome'];record['decoded_output']=None
        if record['outcome']=='ok':
            try:record['decoded_output']=decode_output(case,stdout)
            except (ValueError,UnicodeError) as exc:record.update(outcome='decode_error',decode_error=str(exc))
        self.persist()
        return record


def run_native(archive,out,chosen,tests,compiler,zig):
    # Keep this entry point safe even if invoked directly rather than through main.
    out=out.resolve();archive=archive.resolve();compiler=compiler.resolve()
    if archive.stat().st_size!=ARCHIVE_BYTES or fingerprint(archive)!=ARCHIVE_SHA:
        raise ValueError('not the fixed reviewed official archive')
    whitelist={(case,role):digest for case,c in CASES.items() for role,(_name,digest) in c['sources'].items()}
    if set(chosen)!=set(whitelist) or any(type(chosen[k])is not bytes or hashlib.sha256(chosen[k]).hexdigest()!=h for k,h in whitelist.items()):
        raise ValueError('exact four reviewed sources required')
    runner=ReviewedNativeRunner(out,compiler,zig)
    compiles=[];observations=[];test_rows=[];selection_rows=[];diagnostics=[];version_text='';selected_macros=[]
    try:
        version,stdout,_stderr=runner.diagnostic('version');diagnostics.append(version)
        if version['outcome']!='ok':raise RuntimeError('compiler version query failed')
        version_text=stdout.decode('utf-8',errors='replace')
        macros,stdout,_stderr=runner.diagnostic('macros');diagnostics.append(macros)
        if macros['outcome']!='ok':raise RuntimeError('compiler macro query failed')
        try:macro_text=stdout.decode('ascii')
        except UnicodeError as exc:
            macros.update(outcome='decode_error',decode_error=str(exc));runner.persist()
            raise RuntimeError('compiler macro decoding failed') from exc
        selected_macros=[line for line in macro_text.splitlines() if re.match(r'#define (?:__SIZEOF_INT__|__INT_MAX__|__UINT_MAX__|UINT_MAX|INT_MAX)\b',line)]
        if '#define __SIZEOF_INT__ 4' not in selected_macros or '#define __INT_MAX__ 2147483647' not in selected_macros:
            raise RuntimeError('native target integer-width premise not established')
        for (case,role),data in chosen.items():
            compiled,stdout,stderr=runner.compile_reviewed(case,role,data)
            compiles.append({'case':case,'role':role,'command':compiled['command'],'returncode':compiled['returncode'],
                'stdout':stdout.decode('utf-8',errors='replace'),'stderr':stderr.decode('utf-8',errors='replace'),
                'outcome':compiled['outcome'],'process_index':compiled['index'],'elapsed_seconds':compiled['elapsed_seconds']})
            if compiled['outcome']!='ok':raise RuntimeError('reviewed source compilation failed')
            for x in CASES[case]['domain']:
                observed=runner.observe(case,role,f'{x}\n'.encode());expected=value(case,role,x)
                agrees=observed['outcome']=='ok' and observed['decoded_output']==expected
                observations.append({'case':case,'role':role,'input':x,'expected_model':expected,
                    'native_observed':observed['decoded_output'],'returncode':observed['returncode'],
                    'outcome':observed['outcome'],'process_index':observed['index'],
                    'stderr_empty':observed['stderr_bytes_seen']==0,'agrees':agrees})
                if not agrees:raise RuntimeError('native/model observation disagreement')
        # The fixed requests/domain correspondence and all filename slots precede payload reads.
        selection_rows,valid=read_selected_tests(archive,tests)
        write_json(out/'existing-test-selection-status.json',selection_rows)
        for selection,raw,target in valid:
            case=selection['case'];split=selection['split']
            for role in ('buggy','supplied'):
                observed=runner.observe(case,role,raw)
                test_rows.append({'case':case,'role':role,'split':split,'test_member':selection['test_member'],
                    'input_sha256':selection['input_sha256'],'output_sha256':selection['output_sha256'],
                    'expected_output':target,'native_observed':observed['decoded_output'],'returncode':observed['returncode'],
                    'outcome':observed['outcome'],'process_index':observed['index'],
                    'stderr_empty':observed['stderr_bytes_seen']==0,
                    'matches_existing_expected':observed['outcome']=='ok' and observed['decoded_output']==target})
    finally:
        runner.persist()
        write_json(out/'compile-record.json',{'compiler_version':version_text,'integer_macros':selected_macros,'diagnostics':diagnostics,'compiles':compiles})
        write_json(out/'existing-test-selection-status.json',selection_rows)
        write_csv(out/'native-observations.csv',observations);write_csv(out/'existing-test-observations.csv',test_rows)
    test_outcomes=[]
    for case in CASES:
        for role in ('buggy','supplied'):
            for split in ('repair','heldout'):
                slots=[r for r in selection_rows if r['case']==case and r['split']==split and r['test_member'] is not None]
                executed=[r for r in test_rows if r['case']==case and r['role']==role and r['split']==split]
                test_outcomes.append({'case':case,'role':role,'split':split,'selected':len(slots),
                    'split_available':bool(tests[case][split]),
                    **{s:sum(r['selection_status']==s for r in slots) for s in ('valid','invalid','unavailable')},
                    'total':len(executed),'matched_expected':sum(r['matches_existing_expected'] for r in executed),
                    'execution_errors':sum(r['outcome']!='ok' for r in executed)})
    return {'source_translation_units':4,'compiled_translation_units':len(compiles),
        'domain_process_executions':len(observations),'domain_observation_agreement':sum(r['agrees'] for r in observations),
        'existing_test_executions':sum(r['returncode'] is not None for r in test_rows),
        'existing_test_execution_attempts':len(test_rows),'existing_test_outcomes':test_outcomes}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path)
    p.add_argument('--execute-reviewed',action='store_true');p.add_argument('--compiler',type=Path);p.add_argument('--zig',action='store_true');p.add_argument('--repetitions',type=int,default=30)
    a=p.parse_args()
    # Resolve against the invocation directory before any subprocess changes cwd.
    for field in ('output','archive','compiler'):
        path=getattr(a,field)
        if path is not None:setattr(a,field,path.resolve())
    if not 1<=a.repetitions<=100:raise ValueError('repetition bound')
    if a.output.exists() and any(a.output.iterdir()):raise ValueError('output must be absent or empty')
    if a.execute_reviewed and (not a.archive or not a.compiler or not a.compiler.is_file()):raise ValueError('reviewed execution requires exact archive and local compiler')
    scientific_files=[Path(__file__).resolve(),Path(__file__).with_name('codeflaws_cases.py'),*(ROOT/'src'/s for s in ('producer.py','proof_dag_producer.py','proof_dag_checker.py','refutation_witness_producer.py','refutation_witness_checker.py'))]
    bindings={str(f.relative_to(ROOT)):fingerprint(f) for f in scientific_files}
    pin_affinity();a.output.mkdir(parents=True,exist_ok=True)
    try:
        outcomes,timings=replay_models(a.output,a.repetitions)
        native=None
        if a.archive:
            chosen,tests=inspect(a.archive,a.output)
            if a.execute_reviewed:native=run_native(a.archive,a.output,chosen,tests,a.compiler,a.zig)
    finally:
        changed=[]
        for rel,h in bindings.items():
            try:unchanged=fingerprint(ROOT/rel)==h
            except OSError:unchanged=False
            if not unchanged:changed.append(rel)
        write_json(a.output/'source-binding-check.json',{'source_bindings':bindings,'unchanged':not changed,'changed':changed})
        if changed:raise RuntimeError('scientific source changed during execution')
    cpu_name=None
    if os.name=='nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:cpu_name=winreg.QueryValueEx(k,'ProcessorNameString')[0].strip()
    summary={'environment':{'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'processor_name':cpu_name,'processor_identifier':platform.processor(),'host_logical_cpu_count':os.cpu_count(),'Windows_process_affinity_limit':2 if os.name=='nt' else None},'source_bindings':bindings,'natural_pairs':2,'source_versions_in_case_studies':4,'normalized_requests':len(outcomes),'points_per_request':64,'model_statuses':dict(Counter(r['status'] for r in outcomes)),'full_direct_oracle_agreement':len(outcomes),'full_cells':sum(r['full_cells'] for r in outcomes),'direct_cells':sum(r['direct_cells'] for r in outcomes),'timing_repetitions_per_request':a.repetitions,
        'timing_scope':'decoded receiver API and automated request construction/encoding-to-result workflow including producer for full evidence; manual source inspection/mapping untimed, no network transfer measured',
        'timing_warmups_per_method':{'decoded_api':2,'serialized_workflow':2},
        'operation_count_scope':'separate untimed producer/full/direct/compact/supplied-point callbacks; no operation-count callbacks in timing passes',
        'native':native,'source_admission_executed':bool(a.archive),'source_redistributed':False,'upstream_scripts_executed':False,'native_source_vs_kernel_trace':'stdout decoded observations checked; canonical traces refer to normalized scalar request','raw_outputs_private':True}
    write_json(a.output/'summary.json',summary);print(json.dumps(summary))

if __name__=='__main__':main()
