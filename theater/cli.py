import argparse
import json
import os
from .service import serve, request, live_instances

def main():
    parser=argparse.ArgumentParser(description="Local companion theater")
    parser.add_argument("--socket",help="Explicit local control socket")
    parser.add_argument("--instance",help="Select a running foreground instance ID")
    subs=parser.add_subparsers(dest="op",required=True)
    server=subs.add_parser("serve");server.add_argument("--runtime",required=True);server.add_argument("--port",type=int)
    for op in ("status","catalog","instances"):subs.add_parser(op)
    scene=subs.add_parser("scene");scene.add_argument("name")
    cast=subs.add_parser("cast");cast.add_argument("ids",nargs="+")
    density=subs.add_parser("density");density.add_argument("value",type=int)
    for op in ("pause","resume","quiet","play"):subs.add_parser(op)
    phase=subs.add_parser("phase");phase.add_argument("phase",choices=["idle","working","waiting","ready","blocked"])
    args=parser.parse_args()
    if args.op=="serve":
        serve(args.runtime,args.port);return
    if args.op=='instances':
        print(json.dumps(live_instances(),ensure_ascii=False,indent=2));return
    if not args.socket:
        candidates=[i for i in live_instances() if not args.instance or i['id']==args.instance]
        if len(candidates)==1:args.socket=candidates[0]['socket']
        elif not candidates and not args.instance:args.socket=os.getenv('CODEX_THEATER_SOCKET')
        if not args.socket:parser.error("Select --socket or --instance; use 'instances' to list running windows")
    m={"v":1,"op":args.op}
    if args.op=="scene":m["name"]=args.name
    if args.op=="cast":m["ids"]=args.ids
    if args.op=="density":m["value"]=args.value
    if args.op in ("pause","resume"):m.update(op="pause",value=args.op=="pause")
    if args.op in ("quiet","play"):m.update(op="motion",reduced=args.op=="quiet")
    if args.op=="phase":m.update(op="activity",phase=args.phase)
    print(json.dumps(request(args.socket,m),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
