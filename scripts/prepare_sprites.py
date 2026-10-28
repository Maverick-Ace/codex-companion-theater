#!/usr/bin/env python3
"""Deterministic ImageMagick sprite extraction. Preserve generated alpha.

Source sheets and generation prompts remain alongside the extracted frames.
"""
from pathlib import Path
import subprocess
import json
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def prepare(folder):
    source=folder/"sheet.png"
    with Image.open(source) as im:
        w,h=im.size
        alpha=im.getchannel("A")
        transparency=alpha.getextrema()
        if transparency[0]!=0:raise ValueError(f"no genuine transparent background: {source}")
    dest=folder/"frames";dest.mkdir(exist_ok=True)
    report=[]
    for i in range(16):
        col,row=i%4,i//4
        x0,y0=round(col*w/4),round(row*h/4)
        x1,y1=round((col+1)*w/4),round((row+1)*h/4)
        output=dest/f"{i:02}.png"
        if output.exists():continue
        size="350x315" if i!=15 else "350x265"
        subprocess.run(["convert",str(source),"-crop",f"{x1-x0}x{y1-y0}+{x0}+{y0}","+repage",
                        "-trim","+repage","-resize",size,"-background","none","-gravity","south",
                        "-extent","400x350","-depth","8",str(output)],check=True)
        with Image.open(output) as frame:
            bounds=frame.getchannel("A").getbbox()
            if not bounds:raise ValueError(f"empty sprite {output}")
            report.append({"index":i,"bounds":bounds,"size":frame.size})
    (folder/"extraction.json").write_text(json.dumps({"grid":[4,4],"source_size":[w,h],"frames":report},indent=2))
    print(folder.name,"16 frames ready")

if __name__=="__main__":
    for p in sorted((ROOT/"assets/cast").iterdir()):
        if (p/"sheet.png").exists():prepare(p)
