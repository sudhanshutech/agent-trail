#!/usr/bin/env python3
"""Capture layer: Claude Code transcript -> trail events (JSONL).

Tails a Claude Code session transcript (~/.claude/projects/<slug>/<session>.jsonl)
and emits one trail event per reasoning step, in the schema shared with the viewer:

    {id, parent_id, timestamp, type, label, detail, status}

Claude Code transcripts already form a tree (uuid/parentUuid), so this is mostly a
projection: assistant content blocks (thinking / text / tool_use) become nodes,
tool_result blocks attach under their tool_use, sidechains (subagents) attach under
the Task call that spawned them. Append-only: statuses of in-flight calls are
derived by the viewer, never rewritten here.

Usage:
    claude_code.py <transcript.jsonl> [--out FILE] [--follow]
    claude_code.py --latest [--follow]            # newest transcript on the machine
    claude_code.py --list                         # show recent transcripts
"""
import argparse
import glob
import json
import os
import sys
import time

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
LABEL_LEN = 72

FILE_READ_TOOLS = {"Read", "Glob", "Grep", "NotebookRead"}
FILE_WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SPAWN_TOOLS = {"Task", "Agent"}


def short(text, n=LABEL_LEN):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def tool_label(name, inp):
    """Human-readable one-liner for a tool call."""
    if not isinstance(inp, dict):
        return name
    if desc := inp.get("description"):
        return f"{name}: {short(desc)}"
    for key in ("command", "file_path", "path", "pattern", "query", "url", "prompt", "skill"):
        if key in inp:
            val = inp[key]
            if key == "file_path" or key == "path":
                val = os.path.basename(str(val)) or val
            return f"{name}: {short(val)}"
    return name


def result_text(content):
    """Flatten a tool_result content field to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        return "\n".join(parts)
    return json.dumps(content) if content is not None else ""


class Converter:
    """Stateful transcript-entry -> trail-event projection."""

    def __init__(self, emit):
        self.emit = emit  # callback(event_dict)
        self.tail = {}  # transcript uuid -> id of last trail node for that entry
        self.tool_nodes = {}  # tool_use_id -> trail node id
        self.tool_names = {}  # tool_use_id -> tool name
        self.pending_spawns = []  # Task/Agent tool_use ids awaiting a sidechain
        self.sidechain_root_parent = {}  # sidechain first-uuid -> anchor node id
        self.last_node = None
        self.session_emitted = False

    def node(self, id, parent_id, ts, type, label, detail, status="success"):
        ev = {
            "id": id,
            "parent_id": parent_id,
            "timestamp": ts,
            "type": type,
            "label": label,
            "detail": detail,
            "status": status,
        }
        self.emit(ev)
        self.last_node = id
        return id

    def resolve_parent(self, entry):
        pu = entry.get("parentUuid")
        if pu and pu in self.tail:
            return self.tail[pu]
        if entry.get("isSidechain") and self.pending_spawns:
            # Root of a subagent run: hang it off the Task call that spawned it.
            return self.tool_nodes.get(self.pending_spawns.pop(0), self.last_node)
        return self.last_node

    def feed(self, line):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return
        etype = entry.get("type")
        if etype == "ai-title" and not self.session_emitted:
            self.session_emitted = True
            self.emit(
                {
                    "id": "session",
                    "parent_id": None,
                    "timestamp": None,
                    "type": "session",
                    "label": short(entry.get("aiTitle", "session")),
                    "detail": entry.get("aiTitle", ""),
                    "status": "success",
                }
            )
            return
        if etype not in ("user", "assistant"):
            return
        uuid = entry.get("uuid")
        ts = entry.get("timestamp")
        parent = self.resolve_parent(entry)
        side = " [subagent]" if entry.get("isSidechain") else ""
        msg = entry.get("message") or {}
        content = msg.get("content")

        if etype == "user":
            self._feed_user(entry, uuid, ts, parent, content, side)
        else:
            self._feed_assistant(entry, uuid, ts, parent, content, side)

    def _feed_user(self, entry, uuid, ts, parent, content, side):
        if isinstance(content, str):
            if content.strip() and not content.startswith("<"):  # skip pure meta/command payloads
                self.tail[uuid] = self.node(
                    uuid, parent, ts, "prompt", short(content) + side, content
                )
            else:
                self.tail[uuid] = parent
            return
        if not isinstance(content, list):
            self.tail[uuid] = parent
            return
        cur = parent
        emitted = False
        for i, block in enumerate(content):
            btype = block.get("type")
            if btype == "tool_result":
                tuid = block.get("tool_use_id")
                call_node = self.tool_nodes.get(tuid, cur)
                is_err = bool(block.get("is_error"))
                text = result_text(block.get("content"))
                nid = f"{uuid}:{i}"
                label = short(text) or ("error" if is_err else "ok")
                cur = self.node(
                    nid,
                    call_node,
                    ts,
                    "error" if is_err else "tool_result",
                    label + side,
                    text,
                    "failed" if is_err else "success",
                )
                emitted = True
            elif btype == "text" and block.get("text", "").strip():
                text = block["text"]
                if text.startswith("<"):  # command wrappers / system payloads
                    continue
                nid = f"{uuid}:{i}"
                cur = self.node(nid, cur, ts, "prompt", short(text) + side, text)
                emitted = True
        self.tail[uuid] = cur if emitted else parent

    def _feed_assistant(self, entry, uuid, ts, parent, content, side):
        if not isinstance(content, list):
            self.tail[uuid] = parent
            return
        cur = parent
        fan_base = parent  # parallel tool_use blocks all branch from the same node
        emitted = False
        for i, block in enumerate(content):
            btype = block.get("type")
            nid = f"{uuid}:{i}"
            if btype == "thinking":
                text = block.get("thinking", "")
                if not text.strip():
                    continue
                cur = self.node(nid, cur, ts, "thought", short(text) + side, text)
                fan_base = cur
                emitted = True
            elif btype == "text":
                text = block.get("text", "")
                if not text.strip():
                    continue
                cur = self.node(nid, cur, ts, "text", short(text) + side, text)
                fan_base = cur
                emitted = True
            elif btype == "tool_use":
                name = block.get("name", "tool")
                inp = block.get("input", {})
                if name in FILE_READ_TOOLS:
                    ntype = "file_read"
                elif name in FILE_WRITE_TOOLS:
                    ntype = "file_write"
                else:
                    ntype = "tool_call"
                detail = f"{name}\n{json.dumps(inp, indent=2, ensure_ascii=False)}"
                tid = block.get("id") or nid
                node_id = self.node(
                    tid, fan_base, ts, ntype, tool_label(name, inp) + side, detail, "active"
                )
                self.tool_nodes[tid] = node_id
                self.tool_names[tid] = name
                if name in SPAWN_TOOLS:
                    self.pending_spawns.append(tid)
                cur = node_id
                emitted = True
        self.tail[uuid] = cur if emitted else parent


def iter_lines(path, follow):
    """Yield complete lines from path; if follow, keep polling for appends."""
    with open(path, "r") as f:
        buf = ""
        while True:
            chunk = f.read()
            if chunk:
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    yield line
            elif follow:
                time.sleep(0.3)
            else:
                if buf.strip():
                    yield buf
                return


def latest_transcript():
    files = glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl"))
    files = [f for f in files if os.path.getsize(f) > 0]
    if not files:
        sys.exit("no Claude Code transcripts found under " + PROJECTS_DIR)
    return max(files, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", nargs="?", help="path to a Claude Code session .jsonl")
    ap.add_argument("--latest", action="store_true", help="use the most recently modified transcript")
    ap.add_argument("--list", action="store_true", help="list recent transcripts and exit")
    ap.add_argument("--follow", "-f", action="store_true", help="keep tailing for live capture")
    ap.add_argument("--out", "-o", help="write trail events to this file (default: stdout)")
    args = ap.parse_args()

    if args.list:
        files = sorted(
            glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl")),
            key=os.path.getmtime,
            reverse=True,
        )[:15]
        for f in files:
            print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(f)))}  {f}")
        return

    path = args.transcript or (latest_transcript() if args.latest else None)
    if not path:
        ap.error("provide a transcript path, --latest, or --list")
    print(f"capturing: {path}", file=sys.stderr)

    out = open(args.out, "a", buffering=1) if args.out else sys.stdout

    def emit(ev):
        out.write(json.dumps(ev, ensure_ascii=False) + "\n")
        out.flush()

    conv = Converter(emit)
    try:
        for line in iter_lines(path, args.follow):
            conv.feed(line)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
