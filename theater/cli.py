import argparse
import json
import os
from .service import serve, request

def main():
    parser=argparse.ArgumentParser(description="Local companion theater")
    parser.add_argument("--socket",default=os.getenv("CODEX_THEATER_SOCKET"))
    subs=parser.add_subparsers(dest="op",required=True)
    server=subs.add_parser("serve");server.add_argument("--runtime",required=True);server.add_argument("--port",type=int)
    for op in ("status","catalog"):subs.add_parser(op)
    scene=subs.add_parser("scene");scene.add_argument("name")
    cast=subs.add_parser("cast");cast.add_argument("ids",nargs="+")
    density=subs.add_parser("density");density.add_argument("value",type=int)
    for op in ("pause","resume","quiet","play"):subs.add_parser(op)
    phase=subs.add_parser("phase");phase.add_argument("phase",choices=["idle","working","waiting","ready","blocked"])
    args=parser.parse_args()
    if args.op=="serve":
        serve(args.runtime,args.port);return
    if not args.socket:parser.error("--socket or CODEX_THEATER_SOCKET is required")
    m={"v":1,"op":args.op}
    if args.op=="scene":m["name"]=args.name
    if args.op=="cast":m["ids"]=args.ids
    if args.op=="density":m["value"]=args.value
    if args.op in ("pause","resume"):m.update(op="pause",value=args.op=="pause")
    if args.op in ("quiet","play"):m.update(op="motion",reduced=args.op=="quiet")
    if args.op=="phase":m.update(op="activity",phase=args.phase)
    print(json.dumps(request(args.socket,m),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
