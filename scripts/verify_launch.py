#!/usr/bin/env python3
"""Real CLI submission against a loopback test provider; no external model calls."""
import argparse
import base64
import fcntl
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import re
import select
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.service import Theater,UnixServer

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=ROOT/'build/current.json')
    p.add_argument('--output',type=Path,default=ROOT/'build/launch-native')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    binary=json.loads(args.manifest.read_text())['binary'];requests=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length',0)))
            requests.append(self.path) # Never store prompt/auth fields.
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            response={'id':'resp_local_launch','object':'response','status':'completed',
                      'output':[], 'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}
            for kind in ('response.created','response.completed'):
                payload={'type':kind,'response':response}
                self.wfile.write(('event: '+kind+'\ndata: '+json.dumps(payload)+'\n\n').encode())
            self.wfile.flush()
    http=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    layouts=[];flights=[];raw=bytearray();report={}
    with tempfile.TemporaryDirectory(prefix='launch-verify-',dir='/var/tmp') as temp:
        theater=Theater(temp,seed=7);original=theater.command
        def observe(message):
            result=original(message)
            if message.get('op')=='layout':
                layouts.append(message)
                flight=theater.world.snapshot()['flight']
                if flight:flights.append(flight)
            return result
        theater.command=observe
        server=UnixServer(Path(temp)/'control.sock',theater)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        master,slave=pty.openpty()
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,140,1120,1000))
        env=dict(os.environ,TERM='xterm-256color',TERM_PROGRAM='ghostty',CODEX_THEATER_SOCKET=str(Path(temp)/'control.sock'))
        codex_home=Path(temp)/'codex-home';codex_home.mkdir()
        (codex_home/'config.toml').write_text('[projects.'+json.dumps(str(Path.home()))+']\ntrust_level="trusted"\n')
        env['CODEX_HOME']=str(codex_home)
        for key in ('TMUX','TMUX_PANE','ZELLIJ','ZELLIJ_SESSION_NAME','CODEX_THEATER_OWNER_PID'):env.pop(key,None)
        argv=[binary,'--no-daemon','-m','gpt-6.1-sol','-C',str(Path.home()),
              '-c','check_for_update_on_startup=false','-c','model_provider="launch-local"',
              '-c','model_providers.launch-local.name="Local launch verification"',
              '-c',f'model_providers.launch-local.base_url="http://127.0.0.1:{http.server_port}/v1"',
              '-c','model_providers.launch-local.wire_api="responses"',
              '-c','model_providers.launch-local.requires_openai_auth=false']
        proc=subprocess.Popen(argv,stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True,
                              preexec_fn=lambda:fcntl.ioctl(0,termios.TIOCSCTTY,0));os.close(slave)
        def pump(seconds):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline and proc.poll() is None:
                if not select.select([master],[],[],.03)[0]:continue
                try:chunk=os.read(master,262144)
                except OSError:break
                raw.extend(chunk)
                for query,answer in ((b'\x1b[6n',b'\x1b[1;1R'),(b'\x1b[c',b'\x1b[?62;4;22c'),
                    (b'\x1b[14t',b'\x1b[4;1000;1120t'),(b'\x1b[16t',b'\x1b[6;25;8t'),
                    (b'\x1b[18t',b'\x1b[8;40;140t'),(b'\x1b]11;?',b'\x1b]11;rgb:2020/2323/3434\x1b\\')):
                    if query in chunk:os.write(master,answer)
                for m in re.finditer(rb'\x1b_G([^;]*a=q[^;]*);.*?\x1b\\',chunk):
                    ident=re.search(rb'i=(\d+)',m[1])
                    if ident:os.write(master,b'\x1b_Gi='+ident[1]+b';OK\x1b\\')
        try:
            deadline=time.monotonic()+18
            while not layouts and time.monotonic()<deadline:pump(.15)
            pump(.5)
            os.write(master,b'\r');pump(.3)
            report['empty_enter_does_not_launch']=not flights
            os.write(master,b'/model');pump(.3);os.write(master,b'\x1b');pump(.2)
            report['menu_does_not_launch']=not flights
            os.write(master,b'\x05\x15');pump(.2)
            os.write(master,b'\x1b[200~local-launch-check\x1b[201~');pump(.6)
            os.write(master,b'\r')
            deadline=time.monotonic()+12
            while time.monotonic()<deadline and (not flights or flights[-1]['age']<7):pump(.1)
            report['local_provider_received_turn']=bool(requests)
            report['phases']=sorted({f['phase'] for f in flights})
            report['sun_destination']=bool(flights) and all(f['destination']['kind']=='sun' for f in flights)
            ids={m['submission']['id'] for m in layouts if m.get('submission')}
            report['one_submission_id']=len(ids)==1
            report['no_prompt_in_ipc']='local-launch-check' not in json.dumps(layouts)
            report['flights_complete']=report['phases']==['build','ignite','launch','orbit']
            os.write(master,b'\x05\x15/quit');pump(.4);os.write(master,b'\r');pump(20)
            report['exit_code']=proc.poll()
        finally:
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            os.close(master);server.shutdown();server.server_close();http.shutdown();http.server_close()
        report['only_loopback_provider']=True
        report['final_image_clear']=raw.rfind(b'a=d')>raw.rfind(b'a=T')
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        (args.output/'capture.ansi').write_bytes(raw)
        (args.output/'layouts.json').write_text(json.dumps(layouts)+'\n')
        print(json.dumps(report,indent=2))
        assert all(report[k] for k in ('empty_enter_does_not_launch','menu_does_not_launch','local_provider_received_turn',
               'sun_destination','one_submission_id','no_prompt_in_ipc','flights_complete','final_image_clear'))
        assert report['exit_code']==0

if __name__=='__main__':main()
