#!/usr/bin/env python3
"""Real fullscreen CLI pointer/caret check, without submitting a model request."""
import argparse
import base64
import errno
import fcntl
import io
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from theater.geometry import stage_metrics, stage_position
from theater.service import Theater, UnixServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'build/current.json')
    parser.add_argument('--output', type=Path, default=ROOT/'build/pointer-native')
    parser.add_argument('--cwd', type=Path, default=Path.home())
    args = parser.parse_args()
    info = json.loads(args.manifest.read_text())
    binary = Path(info['binary']).resolve()
    version = subprocess.check_output([str(binary), '--version'], text=True).strip()
    if version != 'codex-cli '+info['version']:
        raise SystemExit('Manifest/binary version mismatch')
    args.output.mkdir(parents=True, exist_ok=True)
    layouts = []
    with tempfile.TemporaryDirectory(prefix='theater-pointer-', dir='/var/tmp') as runtime:
        theater = Theater(runtime, seed=7)
        theater.world.next_scene = theater.world.next_roam = theater.world.next_visit = 1000
        original = theater.command
        def observe(message):
            reply = original(message)
            if message.get('op') == 'layout':
                layouts.append(json.loads(json.dumps(message)))
            return reply
        theater.command = observe
        server = UnixServer(Path(runtime)/'control.sock', theater)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 140, 1120, 1000))
        env = dict(os.environ, TERM='xterm-256color', TERM_PROGRAM='ghostty',
                   CODEX_THEATER_SOCKET=str(Path(runtime)/'control.sock'))
        for key in ('TMUX', 'TMUX_PANE', 'ZELLIJ', 'ZELLIJ_SESSION_NAME'):
            env.pop(key, None)
        proc = subprocess.Popen([str(binary), '-c', 'check_for_update_on_startup=false', '-C', str(args.cwd)],
                                stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True,
                                preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        os.close(slave)
        raw = bytearray()
        evidence = {}
        def pump(seconds):
            deadline = time.monotonic()+seconds
            while time.monotonic()<deadline and proc.poll() is None:
                if not select.select([master], [], [], .02)[0]:
                    continue
                try:
                    chunk = os.read(master, 262144)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                raw.extend(chunk)
                if b'\x1b[6n' in chunk:
                    os.write(master, b'\x1b[1;1R')
                if b'\x1b[c' in chunk or b'\x1b[0c' in chunk:
                    os.write(master, b'\x1b[?62;4;22c')
                if b'\x1b[14t' in chunk:
                    os.write(master, b'\x1b[4;1000;1120t')
                if b'\x1b[16t' in chunk:
                    os.write(master, b'\x1b[6;25;8t')
                if b'\x1b[18t' in chunk:
                    os.write(master, b'\x1b[8;40;140t')
                if b'\x1b]11;?' in chunk:
                    os.write(master, b'\x1b]11;rgb:2020/2323/3434\x1b\\')
                for match in re.finditer(rb'\x1b_G([^;]*a=q[^;]*);.*?\x1b\\', chunk):
                    ident = re.search(rb'i=(\d+)', match[1])
                    if ident:
                        os.write(master, b'\x1b_Gi='+ident[1]+b';OK\x1b\\')
        def state():
            return original({'op': 'status'})['state']
        def mouse(x, y, code=35, end='M'):
            visible = next(m for m in reversed(layouts) if m.get('visible', True))
            sx, sy, columns, rows, *_ = map(int, visible['layout_key'].split(':'))
            col, row = sx+int(x*columns)+1, sy+int(y*rows)+1
            os.write(master, f'\x1b[<{code};{col};{row}{end}'.encode())
        try:
            deadline = time.monotonic()+15
            while not any(m.get('visible', True) for m in layouts) and time.monotonic()<deadline:
                pump(.1)
            if not layouts:
                raise RuntimeError('No real CLI layout frames')
            evidence['actual_binary_matches_manifest'] = Path(f'/proc/{proc.pid}/exe').resolve() == binary
            pump(.5)
            geometry = next(m for m in reversed(layouts) if m.get('visible', True))
            before = state()
            size, floor = stage_metrics(len(before['cast']), geometry['width_px'], geometry['height_px'])
            actor = before['cast'][0]
            cx, _, _ = stage_position(actor, 0, len(before['cast']), geometry['width_px'], size, floor)
            px, py = cx/geometry['width_px'], (floor-size*.5)/geometry['height_px']
            # A first layout may precede native input readiness. Wait for the
            # actual mouse event to reach the world before exercising the gesture.
            deadline=time.monotonic()+6
            while True:
                mouse(px, py);pump(.1)
                evidence['hover_state']=state()
                if (evidence['hover_state']['cast'][0]['reaction'] or {}).get('kind')=='hover':break
                if time.monotonic()>=deadline:raise AssertionError('native hover never became ready')
            mouse(px, py, 0); pump(.2)
            evidence['click_state'] = state()
            mouse(px, py, 0, 'm'); pump(.1)
            assert evidence['hover_state']['cast'][0]['reaction']['kind'] == 'hover'
            assert evidence['click_state']['cast'][0]['reaction']['kind'] == 'click'
            # Seed only the local animation lottery, then drive the whole gesture
            # through real SGR events. No pointer command bypasses the CLI.
            with theater.lock:
                theater.world.rng.seed(3)
                theater.world.attention.cooldowns.clear()
            overhead_y = (floor-size*1.05)/geometry['height_px']
            mouse(px, overhead_y); pump(.35)
            evidence['caught_state'] = state()
            assert evidence['caught_state']['pointer']['caught'] == actor['id']
            for offset in (-.07, .07, -.07, .07, -.07):
                mouse(px+offset, overhead_y); pump(.06)
            deadline=time.monotonic()+.6
            while state()['pointer']['caught'] is not None and time.monotonic()<deadline:pump(.03)
            evidence['released_state'] = state()
            evidence['shake_released'] = evidence['released_state']['pointer']['caught'] is None
            assert evidence['shake_released']
            os.write(master, b'companion caret test')
            pump(.6)
            evidence['typing_state'] = state()
            assert all(a['attention'] for a in evidence['typing_state']['cast'])
            first_cursor = next((m['cursor'] for m in reversed(layouts) if m.get('cursor') and m.get('typing')), None)
            os.write(master, b'\x1b[D'*8); pump(.3)
            second_cursor = next((m['cursor'] for m in reversed(layouts) if m.get('cursor') and m.get('typing')), None)
            evidence['caret_positions'] = [first_cursor, second_cursor]
            evidence['caret_moves_left'] = bool(first_cursor and second_cursor and second_cursor['x']<first_cursor['x'])
            os.write(master, b'\x05\x15/'); pump(.3)
            evidence['hidden_layout_observed'] = any(m.get('visible') is False for m in layouts)
            os.write(master, b'\x1b'); pump(.2)
            os.write(master, b'\x05\x15'); pump(.2)
            os.write(master, b'/quit'); pump(.3)
            os.write(master, b'\r'); pump(20)
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            os.close(master)
            server.shutdown(); server.server_close(); thread.join()
        (args.output/'capture.ansi').write_bytes(raw)
        # Keep coordinate-only IPC for audit; the test draft must never occur here.
        encoded = json.dumps(layouts)
        (args.output/'layouts.json').write_text(encoded+'\n')
        payload = bytearray(); frames = []
        for match in re.finditer(rb'\x1b_G([^;]*);(.*?)\x1b\\', raw, re.S):
            head, body = match[1], match[2]
            if b'f=100' in head and b'a=T' in head:
                payload = bytearray()
            if b'm=' not in head or not body:
                continue
            payload.extend(body)
            if b'm=0' in head:
                try:
                    png = base64.b64decode(payload)
                    image = Image.open(io.BytesIO(png)); image.load()
                    frames.append((match.start(), png))
                except (ValueError, OSError):
                    pass
                payload = bytearray()
        if frames:
            (args.output/'last-frame.png').write_bytes(frames[-1][1])
        pointer_events = [e for layout in layouts for e in layout.get('pointer_events', [])]
        evidence.update(version=version, exit_code=proc.returncode, complete_png_frames=len(frames),
                        pointer_events=pointer_events, any_motion_enabled=b'\x1b[?1003h' in raw,
                        any_motion_disabled=b'\x1b[?1003l' in raw,
                        no_draft_in_ipc='companion caret test' not in encoded,
                        final_image_cleared=bool(frames) and raw.rfind(b'a=d')>frames[-1][0],
                        model_request_submitted=False)
        (args.output/'report.json').write_text(json.dumps(evidence, indent=2)+'\n')
        summary = {k:v for k,v in evidence.items() if not k.endswith('_state') and k!='pointer_events'}
        print(json.dumps(summary, indent=2))
        assert evidence['actual_binary_matches_manifest'] and evidence['caret_moves_left']
        assert evidence['any_motion_enabled'] and evidence['any_motion_disabled']
        assert {'move','down','up'}.issubset({e['kind'] for e in pointer_events})
        assert evidence['no_draft_in_ipc'] and evidence['hidden_layout_observed']
        assert evidence['exit_code'] == 0 and evidence['final_image_cleared']


if __name__ == '__main__':
    main()
