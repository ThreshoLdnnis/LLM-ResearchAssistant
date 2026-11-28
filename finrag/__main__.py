import argparse
import json
from pathlib import Path
from .library import query_library, records
from .search import MODES
from .store import documents, download_samples, ingest


def emit(obj):
    print(json.dumps(obj,ensure_ascii=False,indent=2))


def main():
    parser = argparse.ArgumentParser(description="金融文档研究助手")
    sub = parser.add_subparsers(dest="cmd",required=True)
    sub.add_parser("demo",help="下载并校验四份公开样本")
    sub.add_parser("list")
    web = sub.add_parser("serve")
    web.add_argument("--port",type=int,default=8765)
    add = sub.add_parser("add")
    add.add_argument("file",type=Path)
    for name in ("title","company","type","published","year"):
        add.add_argument("--"+name,required=True)
    qa = sub.add_parser("ask")
    qa.add_argument("question")
    qa.add_argument("--mode",choices=MODES,default="bm25")
    qa.add_argument("--doc",action="append")
    qa.add_argument("--generate",action="store_true")
    qa.add_argument("--chunking",choices=("fixed","structure","semantic"),default="structure")
    qa.add_argument("-k",type=int,default=5)
    ex = sub.add_parser("extract")
    ex.add_argument("--doc")
    ex.add_argument("--kind",choices=["financial","narrative","rows"],default="financial")
    ex.add_argument("--metric")
    ex.add_argument("--page",type=int)
    ex.add_argument("--out",type=Path)
    series=sub.add_parser("series",help="从同一文档生成带页码的年度序列及同比")
    series.add_argument("doc")
    series.add_argument("metrics",nargs="+")
    args=parser.parse_args()
    if args.cmd=="demo":
        emit(list(download_samples()))
    elif args.cmd=="list":
        emit(documents())
    elif args.cmd=="add":
        emit(ingest(args.file.read_bytes(),{k:getattr(args,k) for k in ("title","company","type","published","year")}))
    elif args.cmd=="ask":
        emit(query_library(args.question,args.mode,args.generate,args.doc,args.k,args.chunking))
    elif args.cmd=="series":
        from .series import panel
        emit(panel(args.doc,args.metrics))
    elif args.cmd=="extract":
        rows=[r for r in records(args.doc,args.kind) if (not args.metric or r.get("metric")==args.metric)
              and (not args.page or r["page"]==args.page)]
        if args.out:
            args.out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf8")
        else:
            emit(rows)
    elif args.cmd=="serve":
        from .web import app
        app.run(host="127.0.0.1",port=args.port,threaded=False)


if __name__=="__main__":
    main()

