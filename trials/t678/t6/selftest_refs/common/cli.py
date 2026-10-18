import argparse

from tasksync.exporters import export_csv, export_json, export_md, webhook_payload
from tasksync.reader import load_tasks


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tasksync")
    ap.add_argument("--data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("export-json", "export-csv", "report-md", "webhook-payload"):
        sub.add_parser(name).add_argument("out")
    a = ap.parse_args(argv)
    tasks = load_tasks(a.data)
    fn = {"export-json": export_json, "export-csv": export_csv, "report-md": export_md,
          "webhook-payload": webhook_payload}[a.cmd]
    print(f"wrote {fn(tasks, a.out)} tasks to {a.out}")


if __name__ == "__main__":
    main()
