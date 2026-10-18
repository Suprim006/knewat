import argparse
import json

from tinytasks.api import (
    add_tags, archive_task, create_task, delete_task, export_tasks, get_overdue_tasks, reschedule_task,
)


def main():
    ap = argparse.ArgumentParser(prog="tinytasks")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_add.add_argument("--due-in", type=float, required=True, help="seconds from now")

    sub.add_parser("overdue")

    p_del = sub.add_parser("delete")
    p_del.add_argument("id", type=int)

    p_arch = sub.add_parser("archive")
    p_arch.add_argument("id", type=int)

    p_exp = sub.add_parser("export")
    p_exp.add_argument("--out", help="write to this file instead of stdout")

    p_res = sub.add_parser("reschedule")
    p_res.add_argument("id", type=int)
    p_res.add_argument("--due-in", type=float, required=True, help="seconds from now")

    p_tag = sub.add_parser("tag")
    p_tag.add_argument("id", type=int)
    p_tag.add_argument("tags", nargs="+")

    a = ap.parse_args()
    if a.cmd == "add":
        t = create_task(a.title, a.due_in)
        print(f"created task {t.id}: {t.title} (due_at={t.due_at})")
    elif a.cmd == "overdue":
        for t in get_overdue_tasks():
            print(f"{t.id}: {t.title} (due_at={t.due_at})")
    elif a.cmd == "delete":
        print("deleted" if delete_task(a.id) else "no such task")
    elif a.cmd == "archive":
        print("archived" if archive_task(a.id) else "no such task")
    elif a.cmd == "export":
        text = json.dumps(export_tasks(), indent=2)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            print(text)
    elif a.cmd == "reschedule":
        t = reschedule_task(a.id, a.due_in)
        print(f"task {t.id} now due_at={t.due_at}" if t else "no such task")
    elif a.cmd == "tag":
        t = add_tags(a.id, a.tags)
        print(f"task {t.id} tags: {', '.join(t.tags)}" if t else "no such task")


if __name__ == "__main__":
    main()
