"""Owned JSON identity at CLI boundaries under a non-UTF8 host default."""
import json,os,subprocess,sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from proof_dag_producer import produce
from refutation_witness_producer import produce as compact_produce

def request(refuted=False):
    source='unsigned f(unsigned x) { return x; }'
    return dict(id='owned-caf\u00e9',word_bits=32,inputs={'x':[1]},original=source,
                candidate='unsigned f(unsigned x) { return x + 1u; }' if refuted else source,
                reference=source,repair_guard='x == 1u')

def run(script,*args):
    env=dict(os.environ,PYTHONUTF8='0',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-X','utf8=0','-B',str(ROOT/'src'/script),
                           *map(str,args)],env=env,capture_output=True,timeout=15)
    if result.returncode:
        raise AssertionError(result.stderr.decode('utf-8',errors='replace'))
    return result.stdout.decode('utf-8')

class CliUtf8Tests(unittest.TestCase):
    def test_producer_retains_receiver_owned_request_identifier(self):
        req=request()
        with TemporaryDirectory() as folder:
            rp=Path(folder)/'request.json';cp=Path(folder)/'certificate.json'
            rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8')
            run('proof_dag_producer.py',rp,cp)
            self.assertEqual(json.loads(cp.read_text(encoding='utf-8'))['request_id'],req['id'])

    def test_full_checker_reads_the_same_utf8_identity_as_the_request(self):
        req=request();cert=produce(req)
        with TemporaryDirectory() as folder:
            rp=Path(folder)/'request.json';cp=Path(folder)/'certificate.json'
            rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8')
            cp.write_text(json.dumps(cert,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(json.loads(run('proof_dag_checker.py',rp,cp))['status'],'ACCEPT')

    def test_compact_checker_reads_utf8_without_changing_the_body_digest(self):
        req=request(True)
        cert=compact_produce(req,dict(obligation='repair',input=[1],trace=[]))
        with TemporaryDirectory() as folder:
            rp=Path(folder)/'request.json';cp=Path(folder)/'certificate.json'
            rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8')
            cp.write_text(json.dumps(cert,ensure_ascii=False),encoding='utf-8')
            self.assertEqual(json.loads(run('refutation_witness_checker.py',rp,cp))['status'],'REFUTED')

if __name__=='__main__':unittest.main()
