#!/usr/bin/env python3
"""One-command build from a clean official tag export. No in-place checkout changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from migrate import prepare

ROOT=Path(__file__).resolve().parents[1]
SUPPORTED={'0.163.0':'83086188ae0614bd882818ff1aa23f3194962012'}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--version',default='0.163.0');parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.version not in SUPPORTED:sys_exit('Version has no verified adapter profile. Original installation is unchanged.')
    sha=subprocess.check_output(['git','-C',str(args.source),'rev-parse','rust-v'+args.version+'^{commit}'],text=True).strip()
    if sha!=SUPPORTED[args.version]:sys_exit('Official tag commit does not match the supported profile.')
    fingerprint=hashlib.sha256((ROOT/'adapters/codex/companion_bridge.rs').read_bytes()+(ROOT/'scripts/migrate.py').read_bytes()).hexdigest()
    marker=ROOT/'build/current.json'
    if marker.exists():
        old=json.loads(marker.read_text())
        if old.get('adapter_sha256')==fingerprint and Path(old['binary']).is_file():
            print('Current native adapter already built:',old['binary']);return
    with tempfile.TemporaryDirectory(prefix='codex-theater-source-',dir='/var/tmp') as temp:
        source=Path(temp)
        archive=subprocess.Popen(['git','-C',str(args.source),'archive',sha],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=archive.stdout,mode='r|') as stream:stream.extractall(source,filter='data')
        if archive.wait()!=0:sys_exit('Source export failed')
        prepare(source)
        print('Adapter compatible; original checkout and installed CLI unchanged.')
        if args.check:return
        subprocess.run([os.sys.executable,str(ROOT/'scripts/migrate.py'),str(source),'--apply'],check=True)
        env=dict(os.environ)
        env.setdefault('CARGO_TARGET_DIR',str(ROOT/'build/target'))
        env.setdefault('CARGO_BUILD_JOBS','4')
        subprocess.run(['cargo','+1.94.1','build','-p','codex-cli','--bin','codex','--profile','dev-small'],cwd=source/'codex-rs',env=env,check=True)
        binary=ROOT/'build/bin'/f'codex-{args.version}-theater'
        binary.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(env['CARGO_TARGET_DIR'])/'dev-small/codex',binary)
        marker.write_text(json.dumps({'version':args.version,'upstream_commit':sha,'adapter_sha256':fingerprint,'binary':str(binary)},indent=2)+'\n')
        print('Ready:',ROOT/'scripts/codex-theater')

def sys_exit(message):raise SystemExit(message)
if __name__=='__main__':main()
