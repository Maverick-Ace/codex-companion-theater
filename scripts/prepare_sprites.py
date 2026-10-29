#!/usr/bin/env python3
"""Deterministic ImageMagick sprite extraction. Preserve generated alpha.

Source sheets and generation prompts remain alongside the extracted frames.
"""
from pathlib import Path
import subprocess
import json
import re
import tempfile
import argparse
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def clean_cell(source,rect,output):
    """Remove disconnected neighbor fragments touching a sprite-grid edge.

    Keep the main figure even when it reaches the edge. Keep detached internal
    accessories/emotes, rather than indiscriminately keeping only the largest blob.
    """
    x,y,w,h=rect
    with tempfile.TemporaryDirectory() as temp:
        cell=Path(temp)/'cell.png';mask=Path(temp)/'mask.png'
        subprocess.run(['convert',str(source),'-crop',f'{w}x{h}+{x}+{y}','+repage',str(cell)],check=True)
        base=['convert',str(cell),'-alpha','extract','-threshold','12%']
        result=subprocess.run(base+['-define','connected-components:verbose=true','-connected-components','8','null:'],capture_output=True,text=True,check=True)
        components=[]
        for line in (result.stdout+result.stderr).splitlines():
            m=re.search(r'^\s*(\d+): (\d+)x(\d+)\+(\d+)\+(\d+) .*? ([\d.]+) gray\(255\)',line)
            if m:components.append(tuple(map(float,m.groups())))
        main=max(components,key=lambda c:c[-1])[0] if components else None
        # Generated sheets may leave a few transparent pixels between the grid
        # line and the severed neighbor fragment; include this narrow gutter.
        gutter=max(2,round(min(w,h)*.06))
        remove=[str(int(i)) for i,bw,bh,bx,by,area in components if i!=main and
                (bx<=gutter or by<=gutter or bx+bw>=w-gutter or by+bh>=h-gutter)]
        if not remove:
            subprocess.run(['convert',str(cell),str(output)],check=True);return
        subprocess.run(base+['-define','connected-components:mean-color=true','-define',
            'connected-components:remove='+','.join(remove),'-connected-components','8',
            '-morphology','Dilate','Disk:1',str(mask)],check=True)
        subprocess.run(['convert',str(cell),str(mask),'-alpha','off','-compose','CopyOpacity','-composite',
            str(cell),'-compose','DstIn','-composite',str(output)],check=True)

def prepare(folder,rebuild=False):
    source=folder/"sheet.png"
    with Image.open(source) as im:
        w,h=im.size
        alpha=im.getchannel("A")
        transparency=alpha.getextrema()
        if transparency[0]!=0:raise ValueError(f"no genuine transparent background: {source}")
    dest=folder/"frames";dest.mkdir(exist_ok=True)
    if not rebuild and all((dest/f"{i:02}.png").exists() for i in range(16)):
        print(folder.name,"existing frames retained");return
    report=[]
    for i in range(16):
        col,row=i%4,i//4
        x0,y0=round(col*w/4),round(row*h/4)
        x1,y1=round((col+1)*w/4),round((row+1)*h/4)
        output=dest/f"{i:02}.png"
        if output.exists() and not rebuild:continue
        size="350x315" if i!=15 else "350x265"
        clean_cell(source,(x0,y0,x1-x0,y1-y0),output)
        subprocess.run(["convert",str(output),
                        "-trim","+repage","-resize",size,"-background","none","-gravity","south",
                        "-extent","400x350","-depth","8",str(output)],check=True)
        with Image.open(output) as frame:
            bounds=frame.getchannel("A").getbbox()
            if not bounds:raise ValueError(f"empty sprite {output}")
            report.append({"index":i,"bounds":bounds,"size":frame.size})
    (folder/"extraction.json").write_text(json.dumps({"grid":[4,4],"source_size":[w,h],"frames":report},indent=2))
    print(folder.name,"16 frames ready")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument('--rebuild',action='store_true');args=parser.parse_args()
    for p in sorted((ROOT/"assets/cast").iterdir()):
        if (p/"sheet.png").exists():prepare(p,args.rebuild)
