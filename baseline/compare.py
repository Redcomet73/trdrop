"""Strict trace comparator: only explicitly named floating fields get tolerance."""
import argparse
import json
import math
from pathlib import Path

FLOAT_FIELDS = {'fps','frametime_ms','contribution','row_fraction','max_tear_fraction'}
ATOL, RTOL = 1e-9, 1e-12


def compare(a,b,path='$',field=''):
    if isinstance(a,dict) and isinstance(b,dict):
        if a.keys()!=b.keys():
            raise AssertionError(f'{path}: different fields')
        for k in a:
            compare(a[k],b[k],path+'.'+k,k)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):
            raise AssertionError(f'{path}: lengths {len(a)} != {len(b)}')
        for i,(x,y) in enumerate(zip(a,b)):
            compare(x,y,f'{path}[{i}]',field)
    elif field in FLOAT_FIELDS and type(a) in (int,float) and type(b) in (int,float):
        if not (math.isfinite(a) and math.isfinite(b) and abs(a-b)<=ATOL+RTOL*abs(a)):
            raise AssertionError(f'{path}: {a!r} != {b!r}')
    elif type(a)!=type(b) or a!=b:
        raise AssertionError(f'{path}: {a!r} != {b!r}')


def directories(reference,candidate):
    a,b=Path(reference),Path(candidate)
    # Runtime/profiling logs are intentionally outside this semantic subtree.
    left=sorted(p.relative_to(a) for p in a.rglob('*') if p.is_file())
    right=sorted(p.relative_to(b) for p in b.rglob('*') if p.is_file())
    if left!=right:
        raise AssertionError('Different semantic file inventories')
    if not left:
        raise AssertionError('Empty reference directory')
    for name in left:
        if name.suffix=='.json':
            compare(json.loads((a/name).read_text()),json.loads((b/name).read_text()),str(name))
        elif (a/name).read_bytes()!=(b/name).read_bytes():
            raise AssertionError(f'{name}: byte mismatch')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('reference');p.add_argument('candidate')
    args=p.parse_args()
    directories(args.reference,args.candidate)
    print('PASS: semantic files match (discrete/bytes exact; named floats within tolerance)')
