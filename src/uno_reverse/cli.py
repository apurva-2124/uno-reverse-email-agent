"""Development CLI. All submission commands target the synthetic adapter only."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo
from .classifier import evaluate
from .mailbox import FakeMailbox, create_demo
from .models import Profile, digest
from .replies import check_replies
from .storage import Store
from .workflow import Workflow


def output(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parser():
    p = argparse.ArgumentParser(description="Uno Reverse — synthetic-mailbox development preview")
    p.add_argument("--state", type=Path, default=Path.home() / ".local/share/uno-reverse-demo")
    sub = p.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Create a synthetic mailbox and example profile")
    demo.add_argument("--timezone", default="UTC")
    scan = sub.add_parser("scan", help="Read inbox and generate local drafts")
    scope = scan.add_mutually_exclusive_group()
    scope.add_argument("--since", help="ISO date or timestamp (interpreted in workspace timezone)")
    scope.add_argument("--all-inbox", action="store_true")
    scan.add_argument("--archive", action="store_true")
    scan.add_argument("--yes", action="store_true", help="Confirm displayed scope without prompt")
    review = sub.add_parser("review", help="Open the local browser review screen")
    review.add_argument("--port", type=int, default=0)
    review.add_argument("--no-browser", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--run")
    approve = sub.add_parser("approve")
    approve.add_argument("id")
    approve.add_argument("--hash", required=True, help="Hash of the exact plan inspected via status")
    for command in ("send", "exclude", "redraft", "organize"):
        cmd = sub.add_parser(command)
        cmd.add_argument("id")
    edit = sub.add_parser("edit")
    edit.add_argument("id")
    edit.add_argument("--body-file", type=Path)
    edit.add_argument("--company")
    edit.add_argument("--brand")
    edit.add_argument("--archive", action=argparse.BooleanOptionalAction, default=None)
    suppress = sub.add_parser("suppress")
    suppress.add_argument("target", help="Exact address or stable brand ID")
    for command in ("pause", "resume", "reconcile", "check-replies", "export", "evaluate-classifier"):
        sub.add_parser(command)
    undo = sub.add_parser("undo-organization")
    undo.add_argument("run")
    profile = sub.add_parser("profile")
    profile.add_argument("file", type=Path, help="Reviewed JSON profile")
    brands = sub.add_parser("brands")
    brands.add_argument("file", type=Path, help="Reviewed domain → {id,name} mapping; shared IDs merge aliases")
    auto = sub.add_parser("autopilot")
    autosub = auto.add_subparsers(dest="auto_action", required=True)
    enable = autosub.add_parser("enable")
    enable.add_argument("--backfill-since")
    enable.add_argument("--archive", action="store_true")
    enable.add_argument("--daily-cap", type=int, default=25)
    enable.add_argument("--run-cap", type=int, default=10)
    enable.add_argument("--start-hour", type=int, default=0)
    enable.add_argument("--end-hour", type=int, default=24)
    enable.add_argument("--confirm-hash", help="First preview, then pass its hash to activate")
    for command in ("status", "pause", "resume"):
        autosub.add_parser(command)
    worker = sub.add_parser("worker", help="Run enabled synthetic policy while this process stays open")
    worker.add_argument("--once", action="store_true")
    monitor = sub.add_parser("monitor", help="Check replies without sending pitches")
    monitor.add_argument("--once", action="store_true")
    return p


def timestamp(value, timezone):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone))
    return dt.timestamp()


def main(argv=None):
    args = parser().parse_args(argv)
    store = Store(args.state)
    try:
        if args.command == "evaluate-classifier":
            output(evaluate())
            return 0
        if args.command == "demo":
            ZoneInfo(args.timezone)
            mailbox = create_demo(store.directory / "mailbox.json")
            workflow = Workflow(store, mailbox)
            workflow.set_profile(Profile("My Business", "demo.example", "We help teams organize their work.", "https://demo.example/hello", "Alex\nMy Business"))
            workflow.set_brands({"acme.example": {"id": "acme", "name": "Acme"}})
            store.set("timezone", args.timezone)
            output({"state": str(store.directory), "mailbox": mailbox.identity, "next": "ure scan, then ure review (use the same --state)", "synthetic_only": True})
            return 0
        mailbox_path = store.directory / "mailbox.json"
        if not mailbox_path.exists():
            raise ValueError("Run 'ure demo' first. Gmail is not connected in this development milestone.")
        workflow = Workflow(store, FakeMailbox(mailbox_path))
        command = args.command
        if command == "scan":
            since = 0 if args.all_inbox else timestamp(args.since, store.get("timezone", "UTC")) if args.since else workflow.clock() - 7 * 86400
            output({"scope": "inbox", "since": datetime.fromtimestamp(since, ZoneInfo(store.get("timezone", "UTC"))).isoformat(), "messages": len(workflow.mailbox.scan(since)), "archive": args.archive})
            if not args.yes and input("Generate local drafts for this scope? [y/N] ").lower() != "y":
                return 0
            output({"run": workflow.scan(since, args.archive)})
        elif command == "review":
            from .review import serve
            serve(workflow, args.port, not args.no_browser)
        elif command == "status":
            rows = store.candidates(args.run)
            for c in rows:
                c["hash"] = digest(c["plan"])
            output({"paused": store.get("paused"), "synthetic": True, "candidates": rows})
        elif command == "approve":
            workflow.approve(args.id, args.hash)
            output({"approved": args.id})
        elif command in {"send", "exclude", "redraft", "organize"}:
            output({"result": getattr(workflow, command)(args.id)})
        elif command == "edit":
            workflow.edit(args.id, args.body_file.read_text() if args.body_file else None, args.company, args.brand, args.archive)
            output({"updated": args.id, "approval_invalidated": True})
        elif command == "profile":
            workflow.set_profile(Profile(**json.loads(args.file.read_text())))
            output({"profile_version": workflow.profile.version, "policies_invalidated": True})
        elif command == "brands":
            workflow.set_brands(json.loads(args.file.read_text()))
            output({"brands_updated": True, "policies_invalidated": True})
        elif command == "suppress":
            workflow.suppress(args.target)
        elif command in {"pause", "resume", "reconcile"}:
            output({"result": getattr(workflow, command)()})
        elif command == "check-replies":
            events = check_replies(workflow)
            if events:
                output(events)
        elif command == "undo-organization":
            output({"undone": workflow.undo(args.run)})
        elif command == "export":
            output(store.export())
        elif command == "autopilot":
            if args.auto_action == "enable":
                preview = workflow.policy_preview(since=timestamp(args.backfill_since, store.get("timezone", "UTC")) if args.backfill_since else None,
                                                  archive=args.archive, daily_cap=args.daily_cap, run_cap=args.run_cap,
                                                  timezone=store.get("timezone", "UTC"), start_hour=args.start_hour, end_hour=args.end_hour)
                if args.confirm_hash:
                    output({"policy_id": workflow.enable_policy(preview, args.confirm_hash)})
                else:
                    output({"policy": preview, "hash": digest(preview), "next": "Review this policy and example; rerun with identical options and --confirm-hash HASH"})
            elif args.auto_action == "status":
                policy_id, policy = workflow.active_policy()
                output({"policy_id": policy_id, "policy": policy, "paused": store.get("paused"), "last_poll": store.get("last_poll")})
            else:
                getattr(workflow, args.auto_action)()
        elif command in {"worker", "monitor"}:
            while True:
                if command == "worker":
                    results = workflow.tick()
                    if results:
                        output({"submissions": results, "synthetic": True})
                events = check_replies(workflow)
                if events:
                    output(events)
                if args.once:
                    break
                time.sleep(900)
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"ure: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        return 130
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
