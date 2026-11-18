import argparse
import json
from pathlib import Path

from analytics.workflow import init_demo, ingest_label, resume
from analytics.snapshots import load_snapshot

parser = argparse.ArgumentParser(description="Local SQLMesh snapshot and label/backfill workflow")
parser.add_argument("--home", type=Path, default=Path(".local/analytics"))
sub = parser.add_subparsers(dest="command", required=True)
sub.add_parser("init-demo")
add = sub.add_parser("add-label")
add.add_argument("file", type=Path)
sub.add_parser("resume")
load = sub.add_parser("load-snapshot")
load.add_argument("file", type=Path)
args = parser.parse_args()
if args.command == "init-demo":
    result = init_demo(args.home)
elif args.command == "add-label":
    result = ingest_label(args.home, json.loads(args.file.read_text()))
elif args.command == "load-snapshot":
    result = load_snapshot(args.home, args.file)
else:
    result = resume(args.home)
print(f"Publication: {result or 'unchanged'}")
