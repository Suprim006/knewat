import argparse

from tinytasks.api import create_task, delete_task, get_overdue_tasks, quick_add, postpone_task


def main():
    ap = argparse.ArgumentParser(prog="tinytasks")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_add.add_argument("--due-in", type=float, required=True, help="seconds from now")

    sub.add_parser("overdue")

    p_del = sub.add_parser("delete")
    p_del.add_argument("id", type=int)

    p_qa = sub.add_parser("quick-add")
    p_qa.add_argument("title")
    p_pp = sub.add_parser("postpone")
    p_pp.add_argument("id", type=int)
    p_pp.add_argument("hours", type=int)

    sub.add_parser("status")

    a = ap.parse_args()
    if a.cmd == "add":
        t = create_task(a.title, a.due_in)
        print(f"created task {t.id}: {t.title} (due_at={t.due_at})")
    elif a.cmd == "overdue":
        for t in get_overdue_tasks():
            print(f"{t.id}: {t.title} (due_at={t.due_at})")
    elif a.cmd == "delete":
        print("deleted" if delete_task(a.id) else "no such task")
    elif a.cmd == "quick-add":
        t = quick_add(a.title)
        print(f"created task {t.id}: {t.title} (due_at={t.due_at})")
    elif a.cmd == "postpone":
        t = postpone_task(a.id, a.hours)
        print("postponed" if t else "no such task")
    elif a.cmd == "status":
        from tinytasks.storage import load_all
        print(f"{len(load_all())} tasks")



if __name__ == "__main__":
    main()
