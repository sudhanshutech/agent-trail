#!/usr/bin/env python3
"""Smoke test for the Claude Code capture layer.

Runs capture/claude_code.py over the fixture transcript and asserts the
emitted trail is a well-formed tree with the expected event shapes.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "capture", "claude_code.py")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "transcript.jsonl")


def main():
    out = subprocess.run(
        [sys.executable, CAPTURE, FIXTURE],
        capture_output=True, text=True, check=True,
    ).stdout
    events = [json.loads(line) for line in out.splitlines() if line.strip()]

    def check(cond, msg):
        if not cond:
            sys.exit("FAIL: %s\n%s" % (msg, json.dumps(events, indent=2)))

    check(len(events) >= 10, "expected at least 10 events, got %d" % len(events))

    ids = set()
    for ev in events:
        check(ev["id"] not in ids, "duplicate id %r" % ev["id"])
        check(ev["parent_id"] is None or ev["parent_id"] in ids,
              "orphaned parent_id %r on %r" % (ev["parent_id"], ev["id"]))
        ids.add(ev["id"])

    types = [ev["type"] for ev in events]
    check("session" in types, "missing session title event")
    check("prompt" in types, "missing prompt event")
    check("thought" in types, "missing thought event")
    check(types.count("error") == 1, "expected exactly 1 error event")
    check("file_write" in types, "Edit tool should map to file_write")
    check("file_read" in types, "Read/Grep tools should map to file_read")

    # the two parallel tool calls in message a1 must fan out from the same parent
    fan = [ev for ev in events if ev["id"] in ("tu1", "tu2")]
    check(len(fan) == 2 and fan[0]["parent_id"] == fan[1]["parent_id"],
          "parallel tool calls should share a parent")

    err = next(ev for ev in events if ev["type"] == "error")
    check(err["status"] == "failed", "error events must have status failed")

    print("capture smoke OK: %d events, tree intact" % len(events))


if __name__ == "__main__":
    main()
