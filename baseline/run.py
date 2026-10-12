"""Run cases in isolated processes; never bless crashes or auto-update goldens."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import compare


def expected_exports(case):
    """Inventory from existing fixture scheduling and the frozen exporter defaults.

    ExporterQML increments its counter on every exporting processImage call,
    including redraws. It writes one CSV header and one row per such call.
    ImageFormatModel defaults to JPEG; ExportOptionsModel supplies these names.
    No expected pixel bytes or numeric golden values are generated here.
    """
    streams = case['streams']
    frames = min((len(stream) for stream in streams), default=0)
    calls = 0
    if case.get('pipeline'):
        for frame in range(frames):
            if case.get('preview_first') and frame == 0:
                continue
            calls += 1
            if case.get('redraw_at') == frame:
                calls += 1
    return {
        'csv': ({'name': 'trdrop_analysis.csv', 'rows': calls + 1,
                 'columns': 2 * len(streams)} if case.get('csv') and calls else None),
        'images': ([f'exportsequence_{i:010d}.jpg' for i in range(calls)]
                   if case.get('images') else [])
    }


def validate_exports(semantic, expected):
    """Reject missing, empty, extra or truncated exports, even in matching runs."""
    semantic = Path(semantic)
    required = set(expected['images'])
    if expected['csv']:
        required.add(expected['csv']['name'])
    actual = {p.name for p in semantic.iterdir()
              if p.suffix.lower() in {'.csv', '.jpg', '.tiff'}}
    if actual != required:
        raise AssertionError(f'Export inventory mismatch: expected {sorted(required)}, '
                             f'found {sorted(actual)}')
    for name in required:
        path = semantic / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise AssertionError(f'Missing or empty required export: {name}')
    spec = expected['csv']
    if spec:
        with (semantic / spec['name']).open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        if (len(rows) != spec['rows'] or
                any(len(row) != spec['columns'] or
                    any(not value.strip() for value in row) for row in rows)):
            raise AssertionError(f'CSV row/column inventory mismatch: {spec["name"]}')


def run(exe, fixtures, output, *, hazards=False, no_trace=False, only=None):
    manifest=Path(fixtures)/'manifest.json';output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    for key,value in {'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OMP_NESTED':'FALSE',
                      'OMP_MAX_ACTIVE_LEVELS':'1','OMP_THREAD_LIMIT':'8'}.items():
        env.setdefault(key,value)
    for case in json.loads(manifest.read_text())['cases']:
        if bool(case.get('hazard'))!=hazards or (only and case['id']!=only):continue
        folder=output/case['id']
        cmd=[str(Path(exe).resolve()),'--fixtures',str(manifest.resolve()),'--case',case['id'],
             '--output',str(folder.resolve())]
        if no_trace:cmd+=['--no-trace']
        try:
            p=subprocess.run(cmd,env=env,capture_output=True,timeout=90)
            code=p.returncode;log=p.stdout+p.stderr
        except subprocess.TimeoutExpired as e:
            code='timeout';log=(e.stdout or b'')+(e.stderr or b'')
        (output/(case['id']+'.log')).write_bytes(log)
        result=dict(case=case['id'],exit_code=code,classification='hazard observation' if hazards else 'regression')
        if code == 0 and not hazards:
            result['expected_exports'] = expected_exports(case)
            validate_exports(folder/'semantic', result['expected_exports'])
        results.append(result)
        (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(result),flush=True)
        if code!=0 and not hazards:raise RuntimeError(f"Reference failed: {case['id']}: {code}")
    if not results:raise RuntimeError('No cases selected')
    return results


def suites(a,b):
    a,b=Path(a),Path(b)
    aa=json.loads((a/'results.json').read_text());bb=json.loads((b/'results.json').read_text())
    compare.compare(aa,bb)
    for r in aa:
        for root in (a, b):
            validate_exports(root/r['case']/'semantic', r['expected_exports'])
        compare.directories(a/r['case']/'semantic', b/r['case']/'semantic')
    print('PASS: all semantic traces and bytes match')


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True)
    r=sub.add_parser('capture');r.add_argument('executable');r.add_argument('fixtures');r.add_argument('output')
    r.add_argument('--hazards',action='store_true');r.add_argument('--no-trace',action='store_true');r.add_argument('--only')
    r=sub.add_parser('compare');r.add_argument('reference');r.add_argument('candidate')
    a=p.parse_args()
    if a.mode=='capture':run(a.executable,a.fixtures,a.output,hazards=a.hazards,no_trace=a.no_trace,only=a.only)
    else:suites(a.reference,a.candidate)
