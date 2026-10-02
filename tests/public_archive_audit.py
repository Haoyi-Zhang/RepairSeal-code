"""Audit a frozen 300-record slice of the official Codeflaws defect index.

This is an archival identity/provenance audit.  It deliberately does not claim
that the source archive was downloaded, compiled, or checked in this run.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'public-data'/'codeflaws-first-300.tsv'
COMMIT='aefae75d8546b5e49e7d9489d51a908d5ee9eddd'
BLOB_SHA='7220c1aa33df1a55b25cd7cbb0a554f1a95afb99'
PATTERN=re.compile(r'^(?P<contest>[0-9]+)-(?P<problem>[A-Z0-9]+)-bug-(?P<buggy>[0-9]+)-(?P<fixed>[0-9]+)$')

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--input',type=Path,default=DEFAULT); parser.add_argument('--output',type=Path,default=ROOT/'proof-data'/'codeflaws-archive-audit.json'); args=parser.parse_args()
    raw=args.input.read_bytes(); lines=raw.decode('utf-8').splitlines(); assert len(lines)==300
    records=[]; failures=Counter(); tags=Counter(); contests=Counter(); problems=Counter()
    for ordinal,line in enumerate(lines,1):
        fields=line.split('\t'); assert len(fields)==4,(ordinal,fields)
        task,classification,failure,raw_tags=fields; match=PATTERN.fullmatch(task); assert match,(ordinal,task)
        assert classification=='DCCR'; tag_list=[x for x in raw_tags.split('~') if x]
        record={'ordinal':ordinal,'task_id':task,'classification':classification,'failure':failure,'tags':tag_list,
                **match.groupdict(),'canonical_folder':task,
                'buggy_submission_id':match.group('buggy'),'fixed_submission_id':match.group('fixed')}
        records.append(record); failures[failure]+=1; contests[match.group('contest')]+=1; problems[match.group('problem')]+=1; tags.update(tag_list)
    assert len({r['task_id'] for r in records})==300
    summary={'schema':'codeflaws-archive-audit-v1','status':'PASS','record_count':300,'unique_task_ids':300,
             'selection_rule':'first 300 records in repository order from the official defect-detail index at the pinned commit',
             'repository':'codeflaws/codeflaws','commit':COMMIT,'source_path':'all-script/codeflaws-defect-detail-info.txt','source_lines':'1-300','source_blob_sha':BLOB_SHA,
             'local_slice_sha256':hashlib.sha256(raw).hexdigest(),
             'failure_counts':dict(sorted(failures.items())),'tag_counts':dict(tags.most_common()),'distinct_contests':len(contests),'distinct_problem_labels':len(problems),
             'source_execution':{'performed':False,'reason':'The corresponding source directories were not present or acquired in the isolated campaign. No compile/test result is attributed to these 300 records.'},
             'evidentiary_role':'public benchmark identity, provenance, and defect-taxonomy coverage only; not local semantic-certificate evaluation'}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps({'summary':summary,'records':records},indent=2,sort_keys=True)+'\n')
    with args.output.with_suffix('.csv').open('w',newline='') as handle:
        fields=['ordinal','task_id','contest','problem','buggy_submission_id','fixed_submission_id','classification','failure','tags','canonical_folder']
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore'); writer.writeheader()
        for r in records: writer.writerow({**r,'tags':'|'.join(r['tags'])})
    print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__': main()
