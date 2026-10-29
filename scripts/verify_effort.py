#!/usr/bin/env python3
"""Drive genuine Codex reasoning shortcuts in a PTY without submitting a prompt.

Checks metadata synchronization, one-shot Max/Ultra casts, restoration, and the
shared overview shortcut. Evidence is retained under ignored build/effort-check.
"""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theater.service import request
from verify_navigation import clean, launch_profile, child_has_executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', type=Path, default=Path.home())
    parser.add_argument('--manifest', type=Path, help='Validate an isolated candidate without changing the active manifest')
    parser.add_argument('--output', type=Path, help='Evidence directory; defaults to build/effort-check')
    parser.add_argument('--expect-version', help='Require this native CLI version before starting a PTY')
    args = parser.parse_args()
    manifest, profile = launch_profile(args.manifest, args.expect_version)
    output = args.output or ROOT/'build/effort-check'
    output.mkdir(parents=True, exist_ok=True)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 37, 160, 1280, 948))
    env = dict(os.environ, TERM='xterm-256color', TERM_PROGRAM='ghostty')
    env['CODEX_THEATER_MANIFEST']=str(manifest)
    for key in ('TMUX','TMUX_PANE','ZELLIJ','CODEX_THEATER_SOCKET'):
        env.pop(key, None)
    proc = subprocess.Popen([sys.executable, str(ROOT/'scripts/codex-theater'), '-C', str(args.cwd)],
        stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True,
        preexec_fn=lambda:fcntl.ioctl(0, termios.TIOCSCTTY, 0))
    os.close(slave)
    raw = bytearray()
    samples = []
    report = {**profile,'model_request_submitted':False}
    record = None
    initial = None

    def pump(duration):
        deadline = time.monotonic()+duration
        while time.monotonic()<deadline and proc.poll() is None:
            if not select.select([master], [], [], min(.04, max(0, deadline-time.monotonic())))[0]:
                continue
            try:
                chunk = os.read(master, 262144)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            raw.extend(chunk)
            for query, answer in [
                (b'\x1b[6n',b'\x1b[1;1R'),
                (b'\x1b[c',b'\x1b[?62;4;22c'),
                (b'\x1b[0c',b'\x1b[?62;4;22c'),
                (b'\x1b[14t',b'\x1b[4;948;1280t'),
                (b'\x1b[16t',b'\x1b[6;26;8t'),
                (b'\x1b[18t',b'\x1b[8;37;160t'),
                (b'\x1b]11;?',b'\x1b]11;rgb:2020/2323/3434\x1b\\')]:
                if query in chunk:
                    os.write(master,answer)

    def state():
        result = request(record[1]['socket'], {'op':'status'})['state']
        samples.append({k:result.get(k) for k in ('time','effort','spectacle','scene','quiet') } |
                       {'cast':[a['id'] for a in result['cast']]})
        return result

    def shortcut(key):
        old = state().get('effort')
        os.write(master, key)
        deadline = time.monotonic()+2
        current = None
        while time.monotonic()<deadline:
            pump(.08)
            current = state()
            if current.get('effort') != old:
                break
        return current

    def choose_advanced(kind):
        offset=len(raw)
        os.write(master,b'/model')
        pump(.35)
        os.write(master,b'\r')
        pump(.7)
        for _ in range(3):
            visible=clean(bytes(raw[offset:]))
            if 'Select Reasoning Level' in visible:
                break
            offset=len(raw)
            # Current auto model, or All models followed by the current model,
            # is highlighted by upstream's picker.
            os.write(master,b'\r')
            pump(.6)
        else:
            raise RuntimeError('reasoning picker did not open for current model')
        offset=len(raw)
        os.write(master,b'\x1b[F')  # More reasoning is the final standard item.
        pump(.1)
        os.write(master,b'\r')
        pump(.5)
        if 'Advanced Reasoning' not in clean(bytes(raw[offset:])):
            raise RuntimeError('advanced reasoning picker did not open')
        os.write(master,b'\x1b[F' if kind=='ultra' else b'\x1b[H')
        pump(.1)
        # The picker explicitly offers "s session" to avoid durable defaults.
        os.write(master,b's')
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            pump(.1)
            current=state()
            if current.get('effort')==kind:
                return current
        raise RuntimeError('session-only picker selection did not synchronize '+kind)

    def restore_effort():
        if initial is None:
            return
        tiers=['none','minimal','low','medium','high','xhigh','max','ultra','persistent']
        original=initial.get('effort')
        for _ in range(16):
            current=state().get('effort')
            if current==original:
                report['initial_effort_restored']=True
                return
            if current not in tiers or original not in tiers:
                break
            if original=='ultra' and tiers.index(current)<tiers.index(original):
                choose_advanced('ultra')
            else:
                shortcut(b'\x1b.' if tiers.index(current)<tiers.index(original) else b'\x1b,')
        report['initial_effort_restored']=False

    try:
        deadline = time.monotonic()+25
        while time.monotonic()<deadline:
            pump(.1)
            registry = Path.home()/'.cache/codex-companion-theater/instances'
            for file in registry.glob('*.json'):
                try:
                    item = json.loads(file.read_text())
                    if item.get('pid') == proc.pid:
                        record=(file,item)
                        break
                except (OSError, ValueError):
                    continue
            if record and (b'Context' in raw or b'100%' in raw):
                current=state()
                if current.get('effort'):
                    break
        else:
            raise RuntimeError('native startup or effort metadata timed out')
        # The initial footer renders before the shared backend configures the task.
        # Let that baseline settle before exercising genuine user changes.
        pump(2.5)
        initial=state()
        report['binary_process_matches']=child_has_executable(proc.pid,profile['binary'])
        report['baseline_effort']=initial.get('effort')
        report['baseline_has_no_spectacle']=not initial.get('spectacle')
        normal=[a['id'] for a in initial['cast']]
        # Alt+, and Alt+. are the genuine upstream default bindings.
        # First descend below Max so both test changes are real transitions.
        for _ in range(10):
            current=state()
            if current.get('effort') not in ('ultra','max','persistent'):
                break
            shortcut(b'\x1b,')
        max_state=None
        for _ in range(12):
            current=shortcut(b'\x1b.')
            if current.get('effort')=='max':
                max_state=current
                break
        if max_state is None:
            raise RuntimeError('model or keymap did not expose a Max tier')
        report['max_not_suppressed_by_shortcut_typing']=not max_state.get('quiet',False)
        report['max_cast_preserved']=[a['id'] for a in max_state['cast']]==normal
        report['max_one_shot_started']=(max_state.get('spectacle') or {}).get('kind')=='max'
        pump(1.6)
        later=state()
        report['max_did_not_restart']=(later.get('spectacle') or {}).get('age',0)>.8
        ultra=choose_advanced('ultra')
        report['ultra_not_suppressed_by_picker_typing']=not ultra.get('quiet',False)
        report['ultra_effort_synchronized']=ultra.get('effort')=='ultra'
        report['ultra_all_seventeen']=len(ultra['cast'])==17
        report['ultra_one_shot_started']=(ultra.get('spectacle') or {}).get('kind')=='ultra'
        duration=(ultra.get('spectacle') or {}).get('duration',10)
        pump(min(16,float(duration)+1.5))
        restored=state()
        report['ultra_restores_cast']=[a['id'] for a in restored['cast']]==normal and not restored.get('spectacle')
        restore_effort()
        pump(1.1)
        offset=len(raw)
        os.write(master,b'\x1b[D')
        pump(1.8)
        report['overview_after_left']='Agent command center' in clean(bytes(raw[offset:]))
        os.write(master,b'\x1b')
        pump(1.2)
        os.write(master,b'\x03')
        pump(.8)
        if proc.poll() is None:
            os.write(master,b'\x03')
            pump(1)
        report['exit_code']=proc.poll()
        report['passed']=all(value is True for key,value in report.items() if key not in
                             ('manifest','binary','native_version','model_request_submitted','baseline_effort','exit_code')) and report['exit_code']==0
    except Exception as exc:
        report.update(passed=False,error=str(exc))
    finally:
        if proc.poll() is None and initial is not None and not report.get('initial_effort_restored'):
            try:
                restore_effort()
            except (OSError,ValueError,KeyError):
                report['initial_effort_restored']=False
        if proc.poll() is None:
            os.write(master,b'\x1b')
            pump(.2)
            for _ in range(2):
                if proc.poll() is not None:
                    break
                os.write(master,b'\x03')
                pump(.8)
        if proc.poll() is None:
            # Terminate only this launcher's children and let its finally clean
            # the registry/runtime. Killing the wrapper first would skip that.
            try:
                children=[int(p) for p in Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split()]
            except OSError:
                children=[]
            for pid in children:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        os.close(master)
        report['instance_removed']=bool(record) and not record[0].exists()
        report['passed']=report.get('passed',False) and report['instance_removed']
        (output/'capture.ansi').write_bytes(raw)
        (output/'samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n')
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report.get('passed') else 1


if __name__=='__main__':
    sys.exit(main())
