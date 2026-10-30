#!/usr/bin/env python3
"""Reproducible local CPU, frame traffic and resize-memory measurements. No model calls."""
import argparse,json,os,resource,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.service import Theater

CASES=('idle','walk','working','typing','orbit','paused','reduced','resize')

def measure(case,frames):
    clock=[100.]
    with tempfile.TemporaryDirectory() as root, patch('theater.service.time.monotonic',side_effect=lambda:clock[0]):
        t=Theater(Path(root)/'runtime',seed=23,collection_path=Path(root)/'collection.json');w=t.world
        w.next_scene=w.next_roam=w.next_visit=10000;w.play.next_social=10000;w.life.next_treasure=10000
        if case=='walk':
            for i,a in enumerate(w.actors):a.target=.9 if i%2 else .1
        if case=='working':w.activity('working')
        if case=='paused':w.paused=True
        if case=='reduced':w.reduced_motion=True
        if case=='orbit':w.submit('sol')
        # Keep the rendering workload identical across baseline and optimized code.
        for i,a in enumerate(w.actors):
            a.x=.2+i*.2;a.target=(.9 if i%2 else .1) if case=='walk' else a.x
            if hasattr(a,'depth'):a.depth=a.depth_target=0
        w.rng.seed(23)
        seen=set();traffic=0;durations=[]
        msg={'op':'layout','layout_key':'bench','width_px':1040,'height_px':180,'phase':'working' if case=='working' else 'idle'}
        if case=='typing':msg.update(typing=True,cursor={'x':.61,'y':1.1})
        for i in range(frames+6):
            clock[0]+=1/30
            if case=='orbit':w.flight={'start':w.t-4.6,'destination':{'kind':'sun','color':'#ffbd53','light':'#fff1a8','name':'太阳'},'model':'sol'}
            if case=='resize':msg['height_px']=80+i%121;msg['layout_key']='size-'+str(msg['height_px'])
            cpu=time.process_time();reply=t.command(msg);elapsed=(time.process_time()-cpu)*1000
            if i<6:continue
            durations.append(elapsed)
            if reply['frame_id'] not in seen:
                traffic+=Path(reply['frame']).stat().st_size;seen.add(reply['frame_id'])
        return {'case':case,'requests':frames,'cpu_ms_per_request':round(sum(durations)/len(durations),3),
                'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
                'new_frames':len(seen),'png_mib':round(traffic/1024**2,3),
                'source_cache_entries':len(t.renderer.cache),'mesh_cache_entries':len(t.renderer.rig.grids)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=CASES);p.add_argument('--frames',type=int,default=120);p.add_argument('--output',type=Path)
    a=p.parse_args()
    # Pin children to one allowed core so heterogeneous CPU scheduling cannot skew A/B results.
    if hasattr(os,'sched_getaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if a.case:print(json.dumps(measure(a.case,a.frames)));return
    results=[]
    for case in CASES:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--case',case,'--frames',str(a.frames)],check=True,text=True,capture_output=True)
        row=json.loads(result.stdout);results.append(row);print(json.dumps(row),flush=True)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
