#!/usr/bin/env python3
"""Check the actual launcher: shared overview navigation AND companion rendering.

No model request is submitted. Captures stay in the ignored build directory.
"""
import argparse
import errno
import fcntl
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
import termios
import time

ROOT=Path(__file__).resolve().parents[1]

def launch_profile(manifest=None, expected_version=None):
    path=Path(manifest or os.getenv('CODEX_THEATER_MANIFEST') or ROOT/'build/current.json').resolve()
    info=json.loads(path.read_text())
    binary=Path(info['binary']).resolve()
    version=subprocess.check_output([str(binary),'--version'],text=True,timeout=10).strip()
    if expected_version and version != 'codex-cli '+expected_version:
        raise ValueError(f'Expected codex-cli {expected_version}, found {version}')
    if info.get('version') and version != 'codex-cli '+info['version']:
        raise ValueError('Manifest version does not match its native executable')
    return path,{'manifest':str(path),'binary':str(binary),'native_version':version}

def child_has_executable(parent, binary):
    try:
        children=Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
    except OSError:
        return False
    for pid in children:
        try:
            if Path(f'/proc/{pid}/exe').resolve()==Path(binary):
                return True
        except OSError:
            continue
    return False

def clean(raw):
    raw=re.sub(rb'\x1b_G.*?\x1b\\',b'',raw,flags=re.S)
    raw=re.sub(rb'\x1b\](?:[^\x07\x1b]|\x1b(?!\\))*(?:\x07|\x1b\\)',b'',raw)
    return re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]',b'',raw).decode('utf-8','replace')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd',type=Path,default=Path.home(),help='An already trusted Codex directory')
    parser.add_argument('--manifest',type=Path,help='Validate an isolated candidate without changing the active manifest')
    parser.add_argument('--output',type=Path,help='Evidence directory; defaults to build/navigation-check')
    parser.add_argument('--expect-version',help='Fail before startup unless the native executable has this version')
    args=parser.parse_args()
    manifest,profile=launch_profile(args.manifest,args.expect_version)
    output=args.output or ROOT/'build/navigation-check';output.mkdir(parents=True,exist_ok=True)
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',37,160,1280,948))
    env=dict(os.environ,TERM='xterm-256color',TERM_PROGRAM='ghostty')
    env['CODEX_THEATER_MANIFEST']=str(manifest)
    for key in ('TMUX','TMUX_PANE','ZELLIJ','CODEX_THEATER_SOCKET'):env.pop(key,None)
    proc=subprocess.Popen([sys.executable,str(ROOT/'scripts/codex-theater'),'-C',str(args.cwd)],
        stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True,
        preexec_fn=lambda:fcntl.ioctl(0,termios.TIOCSCTTY,0))
    os.close(slave)
    raw=bytearray();ready=None;events={};start=time.monotonic();record=None;control_ok=False;binary_seen=False
    try:
        while time.monotonic()-start<35:
            if proc.poll() is not None:break
            if select.select([master],[],[],.04)[0]:
                try:chunk=os.read(master,262144)
                except OSError as exc:
                    if exc.errno==errno.EIO:break
                    raise
                if not chunk:break
                raw.extend(chunk)
                if ready is None and (b'Context' in raw or b'100%' in raw):ready=time.monotonic()
                if b'\x1b[6n' in chunk:os.write(master,b'\x1b[1;1R')
                if b'\x1b[c' in chunk or b'\x1b[0c' in chunk:os.write(master,b'\x1b[?62;4;22c')
                if b'\x1b[14t' in chunk:os.write(master,b'\x1b[4;948;1280t')
                if b'\x1b[16t' in chunk:os.write(master,b'\x1b[6;26;8t')
                if b'\x1b[18t' in chunk:os.write(master,b'\x1b[8;37;160t')
                if b'\x1b]11;?' in chunk:os.write(master,b'\x1b]11;rgb:2020/2323/3434\x1b\\')
            if ready is None:continue
            elapsed=time.monotonic()-ready
            if elapsed>1 and 'control' not in events:
                events['control']=len(raw)
                binary_seen=child_has_executable(proc.pid,profile['binary'])
                registry=Path.home()/'.cache/codex-companion-theater/instances'
                for file in registry.glob('*.json'):
                    try:
                        item=json.loads(file.read_text())
                        if item.get('pid')==proc.pid:record=(file,item);break
                    except (ValueError,OSError):continue
                if record:
                    message={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
                        'name':'theater_status','arguments':{'instance_id':record[1]['id']}}}
                    result=subprocess.run([sys.executable,str(ROOT/'plugin/scripts/mcp_server.py')],
                        env=env,input=json.dumps(message)+'\n',text=True,capture_output=True,timeout=3)
                    reply=json.loads(result.stdout).get('result',{})
                    control_ok=result.returncode==0 and reply.get('isError') is False
            for second,name,key in [(2,'left',b'\x1b[D'),(4.5,'back',b'\x1b'),
                                    (8,'quit',b'\x03'),(9,'quit_again',b'\x03')]:
                if elapsed>=second and name not in events:
                    events[name]=len(raw);os.write(master,key)
            if elapsed>10:break
    finally:
        if proc.poll() is None:
            # Only descendants of this test-owned launcher are eligible for cleanup.
            try:children=[int(p) for p in Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split()]
            except OSError:children=[]
            for pid in children:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
            proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        os.close(master)
    raw=bytes(raw);(output/'capture.ansi').write_bytes(raw)
    left=events.get('left',len(raw));back=events.get('back',len(raw))
    before=len(re.findall(rb'\x1b_G[^;]*a=T[^;]*f=100',raw[:left]))
    after=len(re.findall(rb'\x1b_G[^;]*a=T[^;]*f=100',raw[back:]))
    last_frame=raw.rfind(b'a=T')
    report={**profile,'binary_process_matches':binary_seen,
            'ready':ready is not None,'dashboard_after_left':'Agent command center' in clean(raw[left:back]),
            'frames_before_overview':before,'frames_after_return':after,'mcp_without_foreground_env':control_ok,
            'exit_code':proc.returncode,'final_image_clear':raw.rfind(b'a=d')>last_frame>=0,
            'instance_removed':bool(record) and not record[0].exists(),'model_request_submitted':False}
    report['passed']=all((binary_seen,report['dashboard_after_left'],before>0,after>0,control_ok,
                          proc.returncode==0,report['final_image_clear'],report['instance_removed']))
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())
