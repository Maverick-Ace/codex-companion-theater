"""One local world per launcher, with Unix JSON v1 and optional loopback preview."""
import io
import json
import os
from pathlib import Path
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .world import World, CAST, NAMES, SCENES
from .render import Renderer, ROOT

MAX_MESSAGE = 65536

def live_instances():
    """Read the same v1 registry as the independently packaged MCP control client."""
    found=[]
    for file in sorted((Path.home()/'.cache/codex-companion-theater/instances').glob('*.json')):
        try:
            item=json.loads(file.read_text())
            if item.get('v')==1 and Path(item['socket']).is_socket():
                found.append({k:item[k] for k in ('id','socket','cwd')})
        except (ValueError,KeyError,TypeError,OSError):
            continue
    return found

def sixel_cache_entries(directory, stem):
    return directory.glob(f"{stem}_h*_v2.six")

def request(path, message, timeout=1):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        sock.sendall(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        with sock.makefile("rb") as file:
            return json.loads(file.readline(MAX_MESSAGE))

class Theater:
    def __init__(self, runtime, seed=None):
        self.runtime = Path(runtime).resolve()
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.world = World(seed)
        self.renderer = Renderer()
        self.lock = threading.RLock()
        self.last = time.monotonic()
        self.frame_id = 0
        self.last_geometry = None

    def advance(self):
        now = time.monotonic()
        self.world.tick(now-self.last)
        self.last = now

    def command(self, message):
        with self.lock:
            if message.get("v", 1) != 1:
                raise ValueError("unsupported protocol version")
            self.advance()
            op = message.get("op", "status")
            if op == "layout":
                # The TUI sends only display metadata; never a draft or conversation.
                self.world.activity(message.get("phase"), message.get("model"), message.get("typing",False))
                key = str(message["layout_key"])
                if not message.get("visible", True):
                    return {"v":1,"visible":False,"layout_key":key}
                width, height = int(message["width_px"]), int(message["height_px"])
                if not (80 <= width <= 2560 and 48 <= height <= 480):
                    raise ValueError("invalid frame dimensions")
                image = self.renderer.frame(self.world.snapshot(), width, height)
                # A bounded ring. Atomic rename prevents the CLI reading an incomplete PNG.
                self.frame_id += 1
                path = self.runtime / f"frame-{self.frame_id % 64:02}.png"
                sixel=self.runtime/"sixel"
                if sixel.exists():
                    for cached in sixel_cache_entries(sixel,path.stem):
                        cached.unlink(missing_ok=True)
                temp = path.with_suffix(".new")
                image.save(temp, format="PNG", compress_level=2)
                os.replace(temp, path)
                self.last_geometry = {k:message[k] for k in ("layout_key","width_px","height_px")}
                return {"v":1,"visible":True,"layout_key":key,"frame":str(path),"frame_id":self.frame_id}
            if op == "cast":
                self.world.set_cast(message["ids"])
            elif op == "scene":
                self.world.start_scene(message["name"])
            elif op == "pause":
                self.world.paused = bool(message.get("value",True))
            elif op == "motion":
                self.world.reduced_motion = bool(message.get("reduced",True))
            elif op == "density":
                self.world.density = max(1,min(5,int(message["value"])))
                self.world._populate(self.world.pool[:self.world.density])
            elif op == "activity":
                event = message.get("event")
                phase = {"UserPromptSubmit":"working", "PreToolUse":"working", "PermissionRequest":"waiting",
                         "Stop":"ready", "Interrupt":"idle", "SessionStart":"idle"}.get(event, message.get("phase"))
                self.world.activity(phase, message.get("model"), message.get("typing",False))
            elif op not in ("status","catalog","hello"):
                raise ValueError("unknown command")
            return {"v":1,"ok":True,"state":self.world.snapshot(),"geometry":self.last_geometry,
                    "catalog":[{"id":k,"name":NAMES[k]} for k in CAST],"scenes":["roam"]+list(SCENES)}

class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    def __init__(self,path,theater):
        self.theater = theater
        super().__init__(str(path),UnixHandler)
        os.chmod(path,0o600)

class UnixHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(1)
        line = self.rfile.readline(MAX_MESSAGE+1)
        if not line or len(line)>MAX_MESSAGE:
            return
        try:
            result = self.server.theater.command(json.loads(line))
        except (ValueError, KeyError, OSError, TypeError) as exc:
            result = {"v":1,"ok":False,"error":str(exc)}
        self.wfile.write(json.dumps(result,ensure_ascii=False).encode()+b"\n")

def make_http(theater, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def send(self,data,kind="application/json",code=200):
            self.send_response(code)
            self.send_header("Content-Type",kind)
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send((ROOT/"web/index.html").read_bytes(),"text/html; charset=utf-8")
            elif parsed.path == "/api/status":
                self.send(json.dumps(theater.command({"op":"status"}),ensure_ascii=False).encode())
            elif parsed.path == "/api/frame":
                args = parse_qs(parsed.query)
                w = max(400,min(1600,int(args.get("w",[1200])[0])))
                with theater.lock:
                    theater.advance()
                    labels = args.get("labels", ["0"])[0] == "1"
                    im = theater.renderer.frame(theater.world.snapshot(),w,220,labels=labels)
                    data=io.BytesIO();im.save(data,format="PNG",compress_level=1)
                self.send(data.getvalue(),"image/png")
            elif parsed.path.startswith("/portrait/"):
                name = parsed.path.rsplit("/",1)[1]
                if name not in CAST:
                    self.send(b"not found","text/plain",404);return
                self.send((ROOT/"assets/cast"/name/"frames/00.png").read_bytes(),"image/png")
            else:
                self.send(b"not found","text/plain",404)
        def do_POST(self):
            # Loopback preview only. Refuse browser cross-origin control requests.
            origin=self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                self.send(b"forbidden","text/plain",403);return
            if self.path != "/api/control":
                self.send(b"not found","text/plain",404);return
            try:
                n=int(self.headers.get("Content-Length",0))
                if n>MAX_MESSAGE:raise ValueError("message too large")
                reply=theater.command(json.loads(self.rfile.read(n)))
                self.send(json.dumps(reply,ensure_ascii=False).encode())
            except (ValueError,KeyError,OSError) as exc:
                self.send(json.dumps({"error":str(exc)}).encode(),code=400)
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)

def serve(runtime, port=None):
    theater=Theater(runtime)
    path=Path(runtime)/"control.sock"
    if path.exists():
        raise RuntimeError(f"socket already exists: {path}; choose a new runtime directory")
    unix=UnixServer(path,theater)
    http=make_http(theater,port) if port is not None else None
    if http:
        threading.Thread(target=http.serve_forever,daemon=True).start()
        print(f"Preview: http://127.0.0.1:{http.server_port}",flush=True)
    print(f"Socket: {path}",flush=True)
    try:
        unix.serve_forever(poll_interval=.2)
    finally:
        unix.server_close()
        path.unlink(missing_ok=True)
        if http:http.shutdown()
