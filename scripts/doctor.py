#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from build_cli import adapter_fingerprint
ROOT=Path(__file__).resolve().parents[1]
SUPPORTED_CLI=['0.163.0','0.165.0']
checks={}
checks['Pillow']=importlib.util.find_spec('PIL') is not None
checks['CJK_font']=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').exists()
cast=json.loads((ROOT/'assets/cast/catalog.json').read_text())['characters']
checks['17_characters']=len(cast)==17
checks['272_frames']=sum((ROOT/'assets/cast'/c['id']/'frames'/f'{i:02}.png').is_file() for c in cast for i in range(16))==272
cast_ids={c['id'] for c in cast}
for name in ('personalities','rigs'):
    path=ROOT/'config'/f'{name}.json'
    checks[f'17_{name}']=path.exists() and set(json.loads(path.read_text()))==cast_ids
for name in ['plugin/plugin.json','plugin/mcp.json','plugin/hooks/events.json','.agents/plugins/marketplace.json']:
    json.loads((ROOT/name).read_text());checks[name]=True
manifest=ROOT/'build/current.json'
checks['native_binary']=False
active_cli=None
if manifest.exists():
    info=json.loads(manifest.read_text());p=Path(info['binary']);checks['native_binary']=p.is_file()
    active_cli=info.get('version')
    try:
        actual=subprocess.check_output([str(p),'--version'],text=True,timeout=10).strip()
        checks['native_version']=active_cli in SUPPORTED_CLI and actual=='codex-cli '+active_cli
    except (OSError,subprocess.SubprocessError):
        checks['native_version']=False
    if p.is_file() and info.get('binary_sha256'):checks['binary_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()==info['binary_sha256']
    fingerprint=adapter_fingerprint(ROOT)
    checks['native_adapter_current']=info.get('adapter_sha256')==fingerprint
print(json.dumps({'checks':checks,'supported_cli':SUPPORTED_CLI,'active_cli':active_cli,'primary_terminal':'Ghostty / Kitty graphics',
                  'plugin_installation':'prepared only; not installed by this project',
                  'all_passed':all(checks.values())},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
