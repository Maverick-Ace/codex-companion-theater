"""One local world per launcher, with Unix JSON v1 and optional loopback preview."""
import json
import math
import os
from pathlib import Path
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .world import World, CAST, NAMES, SCENES, PERSONALITIES
from .render import Renderer, ROOT
from .life import CollectionStore
from .frames import Frames

MAX_MESSAGE = 65536

def display_point(value, *, cursor=True):
    """Validate coordinate-only metadata before applying an input batch."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid display coordinates")
    result = {}
    for field in ('x', 'y'):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError("invalid display coordinates")
        try:
            number = float(number)
        except OverflowError as exc:
            raise ValueError("invalid display coordinates") from exc
        if not math.isfinite(number):
            raise ValueError("invalid display coordinates")
        low, high = (-32.0, 32.0) if cursor else (-2.0, 3.0)
        if not low <= number <= high:
            raise ValueError("display coordinates outside stage limits")
        result[field] = float(number)
    return result

def pointer_batch(events):
    if not isinstance(events, list) or len(events) > 64:
        raise ValueError("invalid pointer event batch")
    result = []
    for event in events:
        if not isinstance(event, dict) or event.get('kind') not in ('move', 'down', 'up', 'leave'):
            raise ValueError("invalid pointer event")
        point = display_point(event, cursor=False) if event['kind'] != 'leave' else {'x': 0.0, 'y': 0.0}
        button = event.get('button', 0)
        if isinstance(button, bool) or not isinstance(button, int) or button not in (0, 1, 2):
            raise ValueError("invalid pointer button")
        result.append(dict(point, kind=event['kind'], button=button))
    return result

def frame_dimensions(message):
    width, height = message['width_px'], message['height_px']
    if (isinstance(width, bool) or isinstance(height, bool)
            or not isinstance(width, int) or not isinstance(height, int)
            or not (80 <= width <= 2560 and 48 <= height <= 480)):
        raise ValueError("invalid frame dimensions")
    return width, height

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
    def __init__(self, runtime, seed=None, collection_path=None):
        self.runtime = Path(runtime).resolve()
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.world = World(seed)
        self.collection = CollectionStore(collection_path)
        self.world.life.owned,self.world.life.selected=self.collection.load()
        self._collection_state=(tuple(sorted(self.world.life.owned)),self.world.life.selected)
        self.renderer = Renderer()
        self.frames=Frames(self.renderer)
        self.published={}
        self.lock = threading.RLock()
        self.last = time.monotonic()
        self.frame_id = 0
        self.last_geometry = None
        self.native_effort = None
        self.native_submission = 0
        self.native_activity = 0

    def advance(self):
        now = time.monotonic()
        if not self.world.life.manual_hour:self.world.life.clock()
        self.world.tick(now-self.last)
        self.last = now

    def save_collection(self):
        life=self.world.life
        current=(tuple(sorted(life.owned)),life.selected)
        if current==self._collection_state:return
        try:
            life.owned,life.selected=self.collection.save(life.owned,life.selected)
        except OSError:
            # Decoration persistence must not interrupt the terminal frame loop.
            life.notice={'text':'本次收藏暂存于当前窗口','until':self.world.t+3}
        self._collection_state=(tuple(sorted(life.owned)),life.selected)

    def command(self, message):
        with self.lock:
            if not isinstance(message, dict):
                raise ValueError("command must be a JSON object")
            if message.get("v", 1) != 1:
                raise ValueError("unsupported protocol version")
            self.advance()
            op = message.get("op", "status")
            if op == "layout":
                # The TUI sends only display metadata; never a draft or conversation.
                key = str(message["layout_key"])
                if not message.get("visible", True):
                    self.world.pointer('leave', 0, 0)
                    return {"v":1,"visible":False,"layout_key":key}
                width, height = frame_dimensions(message)
                cursor = display_point(message.get('cursor'))
                events = pointer_batch(message.get('pointer_events', []))
                self.world.set_geometry(width, height)
                if message.get("effort") is not None:
                    incoming = (message["effort"], bool(message.get("effort_baseline")))
                    if incoming != self.native_effort:
                        # A steady native frame must not undo a manual local preview.
                        baseline = self.native_effort is None or incoming[1]
                        self.world.set_effort(incoming[0], baseline=baseline)
                        self.native_effort = incoming
                self.world.activity(message.get("phase"), message.get("model"), message.get("typing",False), cursor=cursor)
                submission = message.get('submission')
                if isinstance(submission,dict):
                    sequence = submission.get('id')
                    if isinstance(sequence,int) and not isinstance(sequence,bool) and sequence>self.native_submission:
                        self.native_submission = sequence
                        age = submission.get('age_ms',0)
                        if isinstance(age,(int,float)) and 0<=age<3000:
                            self.world.submit(submission.get('model',message.get('model','')))
                activity=message.get('activity')
                if isinstance(activity,dict) and isinstance(activity.get('id'),int) and activity['id']>self.native_activity:
                    self.native_activity=activity['id']
                    self.world.work_event(activity.get('kind','idle'))
                for event in events:
                    self.world.pointer(**event)
                self.save_collection()
                packet=self.frames.get(self.world.snapshot(),width,height,False,time.monotonic())
                # A bounded ring. Atomic rename prevents the CLI reading an incomplete PNG.
                self.frame_id=self.frames.serial
                slot=packet.serial%64;path=self.runtime/f'frame-{slot:02}.png'
                if self.published.get(slot)!=packet.serial or not path.exists():
                    sixel=self.runtime/'sixel'
                    if sixel.exists():
                        for cached in sixel_cache_entries(sixel,path.stem):cached.unlink(missing_ok=True)
                    temp=path.with_suffix('.new');temp.write_bytes(packet.png);os.replace(temp,path)
                    self.published[slot]=packet.serial
                self.last_geometry = {k:message[k] for k in ("layout_key","width_px","height_px")}
                return {"v":1,"visible":True,"layout_key":key,"frame":str(path),"frame_id":packet.serial}
            if op == "cast":
                self.world.set_cast(message["ids"])
            elif op == "scene":
                self.world.life.touch(self.world)
                self.world.start_scene(message["name"])
            elif op == "pause":
                self.world.paused = bool(message.get("value",True))
            elif op == "motion":
                self.world.reduced_motion = bool(message.get("reduced",True))
            elif op == "density":
                self.world.set_density(int(message["value"]))
            elif op == "effort":
                self.world.set_effort(message["value"])
            elif op == "activity":
                cursor = display_point(message.get('cursor'))
                event = message.get("event")
                phase = {"UserPromptSubmit":"working", "PreToolUse":"working", "PermissionRequest":"waiting",
                         "Stop":"ready", "Interrupt":"idle", "SessionStart":"idle"}.get(event, message.get("phase"))
                self.world.activity(phase, message.get("model"), message.get("typing",False),
                                    effort=message.get("effort"), cursor=cursor)
            elif op == 'clock':
                self.world.life.clock(message.get('hour'))
            elif op == 'treasure':
                self.world.life.touch(self.world)
                self.world.life.spawn(self.world)
            elif op == 'decoration':
                self.world.life.select(message['id'])
            elif op == 'play':
                self.world.play.start(self.world,message['kind'])
            elif op == "work":
                self.world.work_event(message['kind'])
            elif op == "submit":
                self.world.activity('working',model=message.get('model'))
                self.world.submit(message.get('model'))
            elif op == "pointer":
                events = pointer_batch(message.get('events', [message]))
                if 'width_px' in message or 'height_px' in message:
                    self.world.set_geometry(*frame_dimensions(message), labels=bool(message.get('labels', False)))
                for event in events:
                    self.world.pointer(**event)
            elif op not in ("status","catalog","hello"):
                raise ValueError("unknown command")
            self.save_collection()
            return {"v":1,"ok":True,"state":self.world.snapshot(),"geometry":self.last_geometry,
                    "catalog":[{"id":k,"name":NAMES[k],**{field:PERSONALITIES[k][field]
                                for field in ("temperament","tempo","accent","gesture","inspiration")}}
                               for k in CAST],"scenes":["roam"]+list(SCENES)}

class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def service_actions(self):
        # Also stop if the launcher was killed without a catchable signal.
        owner = os.environ.get('CODEX_THEATER_OWNER_PID')
        if owner and os.getppid() != int(owner):
            raise SystemExit(0)
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
        try:
            self.wfile.write(json.dumps(result,ensure_ascii=False).encode()+b"\n")
        except (BrokenPipeError,ConnectionResetError):
            # A cancelled/timed-out display request does not warrant a traceback.
            pass

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
                try:
                    w = max(400,min(1600,int(args.get("w",[1200])[0])))
                    h = max(80,min(480,int(args.get("h",[220])[0])))
                except (ValueError, OverflowError):
                    self.send(b'{"error":"invalid frame dimensions"}',code=400)
                    return
                with theater.lock:
                    theater.advance()
                    labels = args.get("labels", ["0"])[0] == "1"
                    theater.world.set_geometry(w,h,labels=labels)
                    packet=theater.frames.get(theater.world.snapshot(),w,h,labels,time.monotonic())
                self.send(packet.png,"image/png")
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
                if not 0 <= n <= MAX_MESSAGE:raise ValueError("invalid message length")
                reply=theater.command(json.loads(self.rfile.read(n)))
                self.send(json.dumps(reply,ensure_ascii=False).encode())
            except (ValueError,KeyError,OSError,TypeError) as exc:
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
