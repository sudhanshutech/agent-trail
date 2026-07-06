#!/usr/bin/env python3
"""Validate trail JSONL files against the schema contract in the README.

Usage: validate_trail.py <trail.jsonl> [more.jsonl ...]

Checks every line: valid JSON, all schema keys present, known type and status,
unique ids, and every parent_id referencing an id that appeared earlier
(the stream must be appendable, so forward references are not allowed).
"""
import json
import sys

TYPES = {
    "session", "prompt", "thought", "text", "tool_call", "tool_result",
    "file_read", "file_write", "decision", "backtrack", "error",
}
STATUSES = {"active", "success", "failed"}
KEYS = {"id", "parent_id", "timestamp", "type", "label", "detail", "status"}


def validate(path):
    errors = []
    seen = set()
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            where = "%s:%d" % (path, lineno)
            try:
                ev = json.loads(line)
            except ValueError:
                errors.append("%s: not valid JSON" % where)
                continue
            missing = KEYS - set(ev)
            if missing:
                errors.append("%s: missing keys %s" % (where, sorted(missing)))
                continue
            if ev["type"] not in TYPES:
                errors.append("%s: unknown type %r" % (where, ev["type"]))
            if ev["status"] not in STATUSES:
                errors.append("%s: unknown status %r" % (where, ev["status"]))
            if ev["id"] in seen:
                errors.append("%s: duplicate id %r" % (where, ev["id"]))
            if ev["parent_id"] is not None and ev["parent_id"] not in seen:
                errors.append("%s: parent_id %r not seen earlier" % (where, ev["parent_id"]))
            if not isinstance(ev["label"], str) or not ev["label"]:
                errors.append("%s: label must be a non-empty string" % where)
            seen.add(ev["id"])
    if not seen:
        errors.append("%s: file contains no events" % path)
    return errors


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    failed = False
    for path in sys.argv[1:]:
        errors = validate(path)
        if errors:
            failed = True
            print("\n".join(errors))
        else:
            print("%s: OK" % path)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
