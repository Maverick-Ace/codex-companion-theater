"""Real CLI: hold frames through IPC delays and bound uploads during input floods. No model calls."""
import argparse,base64,fcntl,hashlib,json,os,pty,re,select,struct,subprocess,sys,tempfile,termios,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from theater.service import Theater,UnixServer
p=argparse.ArgumentParser();p.add_argument('--manifest',default='build/current.json');p.add_argument('--label',default='after');p.add_argument('--delay',type=float,default=.34);a=p.parse_args()
info=json.loads((ROOT/a.manifest).read_text());out=ROOT/'build/render-diagnosis'/a.label;out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='theater-stability-',dir='/var/tmp') as temp:
 root=Path(temp);home=root/'home';home.mkdir();(home/'config.toml').write_text('[projects."/home/guorui"]\ntrust_level="trusted"\n')
 t=Theater(root/'runtime',seed=7,collection_path=root/'collection.json');original=t.command;jitter=False;calls=[]
 def observe(m):
  start=time.monotonic();reply=original(m)
  if m.get('op')=='layout' and m.get('visible',True):
   if jitter:time.sleep(a.delay)
   calls.append({'at':start,'ms':round((time.monotonic()-start)*1000,2),'frame':reply.get('frame_id')})
  return reply
 t.command=observe
 server=UnixServer(root/'runtime/control.sock',t);threading.Thread(target=server.serve_forever,daemon=True).start()
 master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,140,1120,1000))
 env=dict(os.environ,CODEX_HOME=str(home),TERM='xterm-256color',TERM_PROGRAM='ghostty',CODEX_THEATER_SOCKET=str(root/'runtime/control.sock'))
 for k in ('TMUX','TMUX_PANE','ZELLIJ','ZELLIJ_SESSION_NAME','CODEX_THEATER_OWNER_PID'):env.pop(k,None)
 argv=[info['binary'],'--no-daemon','-C','/home/guorui','-c','check_for_update_on_startup=false','-c','model_provider="local"','-c','model_providers.local.name="Local stability check"','-c','model_providers.local.base_url="http://127.0.0.1:9/v1"','-c','model_providers.local.wire_api="responses"','-c','model_providers.local.requires_openai_auth=false']
 proc=subprocess.Popen(argv,stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True,preexec_fn=lambda:fcntl.ioctl(0,termios.TIOCSCTTY,0));os.close(slave)
 wire=bytearray();raw=bytearray();events=[];payload=bytearray();last_clear=None;blanks=[];last_hash=None;duplicates=0
 def pump(seconds):
  global wire,payload,last_clear,last_hash,duplicates
  end=time.monotonic()+seconds
  while time.monotonic()<end and proc.poll() is None:
   if not select.select([master],[],[],.005)[0]:continue
   try:chunk=os.read(master,262144)
   except OSError:break
   now=time.monotonic();raw.extend(chunk);wire.extend(chunk)
   for q,r in ((b'\x1b[6n',b'\x1b[1;1R'),(b'\x1b[c',b'\x1b[?62;4;22c'),(b'\x1b[14t',b'\x1b[4;1000;1120t'),(b'\x1b[16t',b'\x1b[6;25;8t'),(b'\x1b[18t',b'\x1b[8;40;140t'),(b'\x1b]11;?',b'\x1b]11;rgb:2020/2323/3434\x1b\\')):
    if q in chunk:os.write(master,r)
   offset=0
   for m in re.finditer(rb'\x1b_G([^;]*);(.*?)\x1b\\',wire,re.S):
    offset=m.end();head,body=m[1],m[2]
    if b'a=q' in head:
     ident=re.search(rb'i=(\d+)',head)
     if ident:os.write(master,b'\x1b_Gi='+ident[1]+b';OK\x1b\\')
    if b'a=d' in head:
     if last_clear is None:last_clear=now
     events.append((now,'delete'))
    if b'a=T' in head:payload=bytearray()
    if body and (b'a=T' in head or b'm=' in head):
     payload.extend(body)
     if b'm=0' in head:
      digest=hashlib.sha256(payload).hexdigest()
      if digest==last_hash:duplicates+=1
      last_hash=digest;events.append((now,'image'))
      if last_clear is not None:blanks.append((now-last_clear)*1000);last_clear=None
   if offset:del wire[:offset]
   elif len(wire)>300000:wire=wire[-20000:]
 try:
  deadline=time.monotonic()+18
  while not any(e=='image' for _,e in events) and time.monotonic()<deadline:pump(.05)
  assert any(e=='image' for _,e in events),'native stage did not start'
  pump(.5);baseline_start=time.monotonic();bytes_before=len(raw);images_before=sum(e=='image' for _,e in events)
  flood_start=time.monotonic()
  while time.monotonic()-flood_start<1.5:
   os.write(master,b'\x1b[<35;100;2M');pump(.008)
  flood_end=time.monotonic();flood_images=sum(e=='image' for _,e in events)-images_before
  jitter=True;pump(max(1.35,a.delay*2.2));jitter=False;pump(max(.8,a.delay*1.4))
  measured_end=time.monotonic();measured_events=events[:];measured_blanks=blanks[:]
  os.write(master,b'\x05\x15/quit');pump(.4);os.write(master,b'\r');pump(20)
  report={'ready':True,'max_blank_ms':round(max(measured_blanks,default=0),1),'duplicate_uploads':duplicates,'flood_fps':round(flood_images/(flood_end-flood_start),1),'mb_per_second':round((len(raw)-bytes_before)/(measured_end-baseline_start)/1e6,2),'layout_calls':len(calls),'exit_code':proc.poll(),'render_delay_ms':round(a.delay*1000),'model_request_submitted':False}
  (out/'report.json').write_text(json.dumps(report,indent=2));(out/'events.json').write_text(json.dumps(measured_events));(out/'calls.json').write_text(json.dumps(calls));print(json.dumps(report,indent=2))
  assert report['max_blank_ms']<100,'visible theater blinked during slow render'
  assert report['duplicate_uploads']<=3,'the same PNG was uploaded repeatedly'
  assert report['flood_fps']<=32,'input flood bypassed the animation frame limit'
  assert report['exit_code']==0,'CLI failed to exit normally'
 finally:
  if proc.poll() is None:proc.terminate()
  try:proc.wait(timeout=3)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
  os.close(master);server.shutdown();server.server_close()
