"""Plugin is self-contained when copied into the plugin cache."""
import json
import os
import socket
from pathlib import Path

def instances():
    found=[]
    for file in sorted((Path.home()/'.cache/codex-companion-theater/instances').glob('*.json')):
        try:
            item=json.loads(file.read_text())
            if item.get('v')==1 and Path(item['socket']).is_socket():
                found.append({k:item[k] for k in ('id','socket','cwd')})
        except (ValueError,KeyError,TypeError,OSError):
            continue
    return found

def send(message,instance_id=None):
    path=os.environ.get("CODEX_THEATER_SOCKET")
    available=instances()
    # A long-lived daemon may retain another window's environment. Prefer live
    # registrations and require explicit selection instead of guessing between them.
    if instance_id is not None or available or not path or not Path(path).is_socket():
        selected=[i for i in available if instance_id is None or i['id']==instance_id]
        if len(selected)!=1:
            return {"ok":False,"error":"Start codex-theater, or select one of the live instance_id values.","instances":available}
        path=selected[0]['socket']
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(.5);sock.connect(path)
        sock.sendall(json.dumps(dict(v=1,**message)).encode()+b"\n")
        with sock.makefile("rb") as f:return json.loads(f.readline(65536))
