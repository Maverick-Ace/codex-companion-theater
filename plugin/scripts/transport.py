"""Plugin is self-contained when copied into the plugin cache."""
import json
import os
import socket

def send(message):
    path=os.environ.get("CODEX_THEATER_SOCKET")
    if not path:
        return {"ok":False,"error":"The theater is not running in this session. Start codex-theater first."}
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(.5);sock.connect(path)
        sock.sendall(json.dumps(dict(v=1,**message)).encode()+b"\n")
        with sock.makefile("rb") as f:return json.loads(f.readline(65536))
