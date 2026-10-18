import argparse

from tasksync.exporters import export_json
from tasksync.reader import load_tasks


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tasksync")
    ap.add_argument("--data", help="path to the tinytasks JSON data file")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_json = sub.add_parser("export-json", help="write all tasks as JSON")
    p_json.add_argument("out")

    a = ap.parse_args(argv)
    tasks = load_tasks(a.data)
    if a.cmd == "export-json":
        n = export_json(tasks, a.out)
        print(f"wrote {n} tasks to {a.out}")


if __name__ == "__main__":
    main()
