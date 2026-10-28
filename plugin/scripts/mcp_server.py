#!/usr/bin/env python3
"""MCP stdio control only. All logs go to stderr; no terminal rendering."""
import json
import sys
from transport import send

TOOLS=[
 {"name":"theater_status","description":"Read local cast and current scene.","inputSchema":{"type":"object","properties":{}}},
 {"name":"theater_scene","description":"Select a local scripted scene. Does not call model APIs.","inputSchema":{"type":"object","properties":{"name":{"type":"string","enum":["roam","chat","cookie","paperball","tea","parade","celebrate"]}},"required":["name"]}},
 {"name":"theater_cast","description":"Choose the local companion roster by character ID.","inputSchema":{"type":"object","properties":{"ids":{"type":"array","items":{"type":"string"},"minItems":1}},"required":["ids"]}},
 {"name":"theater_pause","description":"Pause or resume the local animation.","inputSchema":{"type":"object","properties":{"value":{"type":"boolean"}},"required":["value"]}},
 {"name":"theater_motion","description":"Set reduced motion for the local animation.","inputSchema":{"type":"object","properties":{"reduced":{"type":"boolean"}},"required":["reduced"]}},
]

def handle(m):
    method=m.get("method")
    if method=="initialize":return {"protocolVersion":m.get("params",{}).get("protocolVersion","2024-11-05"),"capabilities":{"tools":{}},"serverInfo":{"name":"companion-theater","version":"0.1.0"}}
    if method=="ping":return {}
    if method=="tools/list":return {"tools":TOOLS}
    if method=="tools/call":
        params=m.get("params",{});name=params.get("name");args=params.get("arguments",{})
        operations={"theater_status":"status","theater_scene":"scene","theater_cast":"cast","theater_pause":"pause","theater_motion":"motion"}
        if name not in operations:raise ValueError("unknown tool")
        # Do not allow arguments to overwrite the mapped operation/version.
        allowed={"theater_status":[],"theater_scene":["name"],"theater_cast":["ids"],"theater_pause":["value"],"theater_motion":["reduced"]}[name]
        reply=send({"op":operations[name],**{k:args[k] for k in allowed if k in args}})
        return {"content":[{"type":"text","text":json.dumps(reply,ensure_ascii=False)}],"isError":reply.get("ok") is False}
    raise ValueError("unsupported method")

def main():
    for line in sys.stdin:
        try:
            m=json.loads(line)
            if "id" not in m:continue
            try:reply={"jsonrpc":"2.0","id":m["id"],"result":handle(m)}
            except (ValueError,KeyError,OSError) as exc:reply={"jsonrpc":"2.0","id":m["id"],"error":{"code":-32602,"message":str(exc)}}
            print(json.dumps(reply,ensure_ascii=False),flush=True)
        except ValueError as exc:print(str(exc),file=sys.stderr)

if __name__=="__main__":main()
