#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
checks={}
checks['Pillow']=importlib.util.find_spec('PIL') is not None
checks['CJK_font']=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').exists()
cast=json.loads((ROOT/'assets/cast/catalog.json').read_text())['characters']
checks['17_characters']=len(cast)==17
checks['272_frames']=sum((ROOT/'assets/cast'/c['id']/'frames'/f'{i:02}.png').is_file() for c in cast for i in range(16))==272
for name in ['plugin/plugin.json','plugin/mcp.json','plugin/hooks/events.json','.agents/plugins/marketplace.json']:
    json.loads((ROOT/name).read_text());checks[name]=True
manifest=ROOT/'build/current.json'
checks['native_binary']=False
if manifest.exists():
    info=json.loads(manifest.read_text());p=Path(info['binary']);checks['native_binary']=p.is_file()
    if p.is_file() and info.get('binary_sha256'):checks['binary_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()==info['binary_sha256']
print(json.dumps({'checks':checks,'supported_cli':['0.163.0'],'primary_terminal':'Ghostty / Kitty graphics',
                  'plugin_installation':'prepared only; not installed by this project',
                  'all_passed':all(checks.values())},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
