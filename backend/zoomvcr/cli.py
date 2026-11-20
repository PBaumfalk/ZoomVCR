"""zoomvcr command line tool, speaking to the authenticated API."""
import argparse
import json
import os
import sys
from datetime import datetime
import httpx

API = os.getenv("ZOOMVCR_API_URL", "http://localhost:8000/api").rstrip("/")
TOKEN = os.getenv("ZOOMVCR_API_TOKEN", "")

def request(method: str, uri: str, payload=None):
    if not TOKEN:
        raise SystemExit("ZOOMVCR_API_TOKEN is not set")
    with httpx.Client(timeout=30) as client:
        result = client.request(method, API + uri, headers={"Authorization": "Bearer " + TOKEN}, json=payload)
        if result.is_error:
            raise SystemExit(f"{result.status_code}: {result.text[:1000]}")
        return result.json()

def main(argv=None):
    parser = argparse.ArgumentParser(prog="zoomvcr", description="Self-hosted consent-aware video recorder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    ls = sub.add_parser("recordings")
    ls.add_argument("--search", default="")
    schedule = sub.add_parser("schedule")
    schedule.add_argument("--title", required=True)
    schedule.add_argument("--at", required=True, help="Timezone-aware ISO-8601, e.g. 2026-11-07T09:00:00+01:00")
    schedule.add_argument("--minutes", required=True, type=int)
    schedule.add_argument("--source", choices=["synthetic", "desktop_manual"], default="synthetic")
    schedule.add_argument("--url")
    schedule.add_argument("--participant-name", help="Exact name Zoom should display during this meeting")
    schedule.add_argument("--authorization", choices=["host", "written_consent", "other"], help="Authorization basis for Zoom captures")
    schedule.add_argument("--authorization-reference", help="Email date / document reference")
    schedule.add_argument("--permission-confirmed", action="store_true")
    schedule.add_argument("--disclosure-acknowledged", action="store_true")
    rename = sub.add_parser("set-name", help="Change the name of a planned Zoom recording")
    rename.add_argument("id")
    rename.add_argument("--name", required=True)
    for cmd in ("start", "stop", "process", "logs", "admit", "confirm-name"):
        p = sub.add_parser(cmd)
        p.add_argument("id")
    args = parser.parse_args(argv)
    if args.command == "status":
        output = request("GET", "/status")
    elif args.command == "recordings":
        output = request("GET", "/recordings", None)  # URI for untrusted query is URL encoded below
        if args.search:
            output = [x for x in output if args.search.lower() in x["title"].lower()]
    elif args.command == "schedule":
        datetime.fromisoformat(args.at)
        output = request("POST", "/recordings", {"title": args.title, "scheduled_at": args.at, "duration_minutes": args.minutes, "source": args.source, "meeting_url": args.url, "participant_name": args.participant_name,
            "authorization_basis": args.authorization,
            "authorization_reference": args.authorization_reference,
            "permission_confirmed": args.permission_confirmed,
            "disclosure_acknowledged": args.disclosure_acknowledged})
    elif args.command == "set-name":
        output = request("PATCH", f"/recordings/{args.id}/participant-name", {"participant_name": args.name})
    else:
        method, uri = ("GET", f"/recordings/{args.id}/logs") if args.command == "logs" else ("POST", f"/recordings/{args.id}/{args.command}")
        output = request(method, uri)
    print(json.dumps(output, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
