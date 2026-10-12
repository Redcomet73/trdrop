"""Generate packed BGR fixtures without OpenCV, codecs, random libraries or goldens."""
import argparse
import hashlib
import json
from pathlib import Path


def generate(root, large=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    cases = []

    def image(w, h, level=0, rows=None, points=(), color=None):
        data = bytearray(bytes(color or (level,) * 3) * (w * h))
        for y in rows or []:
            data[y*w*3:(y+1)*w*3] = bytes((255,)*3) * w
        for x, y, value in points:
            data[(y*w+x)*3:(y*w+x+1)*3] = bytes((value,)*3)
        return bytes(data)

    def add(name, frames, w=20, h=10, fps=60, threshold=0, dismiss=10,
            videos=None, **options):
        streams = videos or [frames]
        paths = []
        for v, stream in enumerate(streams):
            seq = []
            for data in stream:
                digest = hashlib.sha256(data).hexdigest()
                path = root / (digest + '.bgr')
                if not path.exists():
                    path.write_bytes(data)
                seq.append({'path': path.name, 'sha256': digest})
            paths.append(seq)
        cases.append(dict(id=name, width=w, height=h, fps=fps,
                          threshold=threshold, dismiss=dismiss, streams=paths, **options))

    a, b = image(20, 10), image(20, 10, 255)
    add('empty', [])
    add('single', [a])
    add('identical', [a]*5)
    add('all_changed', [a,b,a,b])
    for fps in (1,24,29.97,30,59.94,60,120,240):
        add('repeat_ring_' + str(fps), [a,a,b,b]*int(fps+2), fps=fps)
    add('long_hold', [a,b,a]+[a]*130+[b])
    for t in (0,1,5,255):
        for delta in sorted(set(max(0,min(255,t+d)) for d in (-1,0,1))):
            add(f'threshold_{t}_{delta}', [a,image(20,10,delta)], threshold=t)
    add('equal_gray_color', [image(20,10,color=(0,0,0)),image(20,10,color=(1,0,0))])
    for where in ('top','bottom'):
        y = 0 if where == 'top' else 9
        for count in (1,2,3):
            add(f'{where}_completeness_{count}', [a,image(20,10,points=[(x,y,255) for x in range(count)])])
    for rows in ([0], [9], list(range(5)), [1,2,5,6,8]):
        for dismiss in (0,9,10,11,49,50,51,100):
            add('tear_'+'_'.join(map(str,rows))+f'_dismiss_{dismiss}',
                [a,image(20,10,rows=rows),b,a], dismiss=dismiss)
    for w,h in ((1,1),(9,1),(9,2),(17,11),(33,3)):
        for padded in (False,True):
            add(f'geometry_{w}_{h}_{padded}',[image(w,h),image(w,h,255)],
                w=w,h=h,padded=padded)
    add('reset_stale_tears',[a,image(20,10,rows=[0,1]),a],reset_at=2)
    add('options_change',[a,image(20,10,1),image(20,10,2)],threshold_at={'2':1})
    add('two_video_legacy',[a,b],videos=[[a,image(20,10,rows=[0,1])],
                                      [a,image(20,10,rows=[1,2,3,4,5])]])
    add('three_video_legacy',[a,b],videos=[[a,b],[a,image(20,10,rows=[0])],[a,b]])
    add('unequal_lengths',[a,b],videos=[[a,b,a],[a,b]])
    add('retained_tears',[a,image(20,10,rows=[0,1])]*35,pipeline=True,draw_tears=False)
    add('pipeline_csv',[a,b,a,b],pipeline=True,csv=True,preview_first=True)
    add('pipeline_images',[a,b,a,b],pipeline=True,images=True,center=False)
    add('pipeline_centered',[a,b,a,b],pipeline=True,csv=True,center=True)
    add('pipeline_redraw',[a,b,a,b],pipeline=True,csv=True,redraw_at=2)
    add('zero_fps',[a,b],fps=0,hazard=True)
    add('reexport',[a,b],pipeline=True,csv=True,reexport=True,hazard=True)
    if large:
        for w,h in ((1280,720),(1920,1080),(3840,2160)):
            add(f'large_{w}',[image(w,h),image(w,h,255)]*3,w=w,h=h)
    manifest = dict(schema=1,pixel_format='BGR24',layout='packed row-major',cases=cases)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('output')
    p.add_argument('--large',action='store_true')
    a=p.parse_args()
    m=generate(a.output,a.large)
    print(f"Generated {len(m['cases'])} cases; no reference outputs generated.")
