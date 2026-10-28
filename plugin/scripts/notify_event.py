#!/usr/bin/env python3
"""Quick optional hook notification; intentionally discard user/tool content."""
import json
import sys
from transport import send
try:
    event=json.loads(sys.stdin.read(1048576))
    clean={k:event[k] for k in ("model",) if k in event}
    clean.update(op="activity",event=event.get("hook_event_name",""))
    send(clean)
except (ValueError,OSError):
    pass
