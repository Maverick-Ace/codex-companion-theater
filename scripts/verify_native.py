#!/usr/bin/env python3
"""PTY contract check: real CLI, real sidecar, no submitted model request."""
import base64
import argparse
import errno
import fcntl
import io
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('binary',nargs='?')
parser.add_argument('--disconnect',action='store_true')
parser.add_argument('--cwd',type=Path,default=Path.home(),help='An already trusted Codex working directory')
args=parser.parse_args()
disconnected=args.disconnect
OUT=ROOT/('artifacts/native-disconnect' if disconnected else 'artifacts/native');OUT.mkdir(exist_ok=True)
binary=args.binary or json.loads((ROOT/'build/current.json').read_text())['binary']
with tempfile.TemporaryDirectory(prefix='theater-pty-',dir='/var/tmp') as runtime:
    log=open(OUT/'engine.log','w')
    engine=subprocess.Popen([sys.executable,'-m','theater.cli','serve','--runtime',runtime],cwd=ROOT,stdout=log,stderr=log)
    deadline=time.monotonic()+4
    while not (Path(runtime)/'control.sock').exists():
        if engine.poll() is not None or time.monotonic()>deadline:raise RuntimeError('sidecar failed')
        time.sleep(.03)
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',37,240,1920,948))
    env=dict(os.environ,TERM='xterm-256color',TERM_PROGRAM='ghostty',CODEX_THEATER_SOCKET=str(Path(runtime)/'control.sock'))
    for key in ['TMUX','TMUX_PANE','ZELLIJ','ZELLIJ_SESSION_NAME']:env.pop(key,None)
    argv=[binary,'--no-daemon','--no-alt-screen','-c','tui.pet="disabled"','-c','check_for_update_on_startup=false','-C',str(args.cwd)]
    proc=subprocess.Popen(argv,stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True,
                          preexec_fn=lambda:fcntl.ioctl(0,termios.TIOCSCTTY,0))
    os.close(slave);data=bytearray();chunks=[];events=[];start=time.monotonic();steps=set();ready=None
    try:
        while time.monotonic()-start<40:
            age=time.monotonic()-(ready if ready is not None else start)
            if proc.poll() is not None:break
            if select.select([master],[],[],.04)[0]:
                try:chunk=os.read(master,262144)
                except OSError as exc:
                    if exc.errno==errno.EIO:break
                    raise
                if not chunk:break
                chunks.append((age,len(data),len(chunk)));data.extend(chunk)
                if ready is None and re.search(rb'\x1b_G[^;]*a=T[^;]*f=100',data):
                    ready=time.monotonic();age=0
                if b'\x1b[6n' in chunk:os.write(master,b'\x1b[1;1R')
                if b'\x1b[c' in chunk or b'\x1b[0c' in chunk:os.write(master,b'\x1b[?62;4;22c')
                if b'\x1b[14t' in chunk:os.write(master,b'\x1b[4;948;1920t')
                if b'\x1b[16t' in chunk:os.write(master,b'\x1b[6;26;8t')
                if b'\x1b[18t' in chunk:os.write(master,b'\x1b[8;37;240t')
                if b'\x1b]11;?' in chunk:os.write(master,b'\x1b]11;rgb:2020/2323/3434\x1b\\')
                for match in re.finditer(rb'\x1b_G([^;]*a=q[^;]*);.*?\x1b\\',chunk):
                    ident=re.search(rb'i=(\d+)',match[1])
                    if ident:os.write(master,b'\x1b_Gi='+ident[1]+b';OK\x1b\\')
            for second,label,action in [
                (3,'typing',lambda:os.write(master,b'hello')),
                (5,'popup',lambda:os.write(master,b'\x15/')),
                (7,'dismiss',lambda:os.write(master,b'\x1b')),
                (7.4,'clear',lambda:os.write(master,b'\x15')),
                (9,'resize',lambda:fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',27,120,960,692))),
                (12,'quit',lambda:os.write(master,b'\x15/quit')),
                (13,'quit_enter',lambda:os.write(master,b'\r'))]:
                if ready is not None and age>second and label not in steps:
                    action();steps.add(label);events.append({'time':age,'name':label,'offset':len(data)})
            if ready is not None and disconnected and age>9.5 and 'disconnect' not in steps:
                engine.terminate();steps.add('disconnect');events.append({'time':age,'name':'disconnect','offset':len(data)})
            if ready is not None and age>16 and 'interrupt' not in steps:
                os.write(master,b'\x04');steps.add('interrupt')
    finally:
        if proc.poll() is None:proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        os.close(master);engine.terminate();engine.wait(timeout=3);log.close()
    raw=bytes(data);(OUT/'capture.ansi').write_bytes(raw)
    # Assemble inline Kitty PNG chunks, ignoring query and delete commands.
    payload=bytearray();frames=[];positions=[]
    for match in re.finditer(rb'\x1b_G([^;]*);(.*?)\x1b\\',raw,re.S):
        head,body=match[1],match[2]
        if b'f=100' in head and b'a=T' in head:
            payload=bytearray();positions.append({'offset':match.start(),'header':head.decode()})
        if b'm=' not in head or not body:continue
        payload.extend(body)
        if b'm=0' in head:
            try:
                png=base64.b64decode(payload)
                image=Image.open(io.BytesIO(png));image.load()
                frames.append({'offset':match.start(),'png':png,'size':image.size})
            except Exception:pass
            payload=bytearray()
    if frames:
        (OUT/'first-frame.png').write_bytes(frames[0]['png'])
        (OUT/'last-frame.png').write_bytes(frames[-1]['png'])
    clean=re.sub(rb'\x1b_G.*?\x1b\\',b'',raw,flags=re.S)
    clean=re.sub(rb'\x1b\](?:[^\x07\x1b]|\x1b(?!\\))*(?:\x07|\x1b\\)',b'',clean)
    clean=re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]',b'',clean)
    (OUT/'text.txt').write_text(clean.decode('utf-8','replace'))
    report={'argv':argv,'exit_code':proc.returncode,'raw_bytes':len(raw),'complete_png_frames':len(frames),
            'frame_sizes':sorted(set(f['size'] for f in frames)),'events':events,'chunks':chunks,
            'unique_frames':len(set(f['png'] for f in frames)),
            'delete_commands':len(re.findall(rb'\x1b_G[^;]*a=d',raw)),
            'final_delete_after_last_frame':bool(frames) and raw.rfind(b'a=d')>frames[-1]['offset'],
            'model_request_submitted':False}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('chunks','argv')},indent=2))
    if len(frames)<10:raise SystemExit('Not enough real CLI frames; inspect capture')
