# agent-trail

[![CI](https://github.com/sudhanshutech/agent-trail/actions/workflows/ci.yml/badge.svg)](https://github.com/sudhanshutech/agent-trail/actions/workflows/ci.yml)

**A live, branching visualization of an agent's reasoning.**

When an agentic coding session runs (Claude Code, or any tool-calling agent), all you normally get is a scrolling wall of text. Debugging an agent means re-reading that wall from the top, hoping to spot the moment it went wrong.

agent-trail renders the shape of the run instead. Every thought, tool call, and decision becomes a node in a growing trail. Failed attempts terminate as grayed-out dead branches. The moment the agent gives up on one approach and pivots to another gets a visible badge. You can watch it live while the agent works, or replay a finished session and scrub through it step by step.

```
prompt - thought - read - edit - test (fails)     <- dead branch, grayed out
                 \
                  pivot - read - edit - test (passes) - decision
```

## Quick start

```bash
python3 server.py
```

That serves the viewer at http://127.0.0.1:7845. It uses only the Python standard library, so there is nothing to install.

Open the URL and click **demo**. A sample branching session ships in `trails/` so you can try the viewer without capturing anything first. From there you can:

- drag to pan and scroll to zoom
- click any node to see its full content (the actual tool call, reasoning text, or result)
- replay with the scrubber, the step buttons, or the space bar, at speeds from 0.5x to instant

### Watch a live Claude Code session

Run these in two terminals:

```bash
# terminal 1: the server
python3 server.py

# terminal 2: tail the newest Claude Code transcript into a trail file
python3 capture/claude_code.py --latest --follow --out trails/my-session.trail.jsonl
```

The session shows up in the sidebar with a green live dot. Open it and nodes animate in as the agent works. If you want a specific session instead of the newest one, `capture/claude_code.py --list` shows recent transcripts.

### Capture a finished session for replay

```bash
python3 capture/claude_code.py ~/.claude/projects/<slug>/<session>.jsonl \
    --out trails/some-name.trail.jsonl
```

## How it works

```
agent run -> capture script -> trail file (append-only JSONL) -> server (SSE) -> viewer
```

The trail file is the entire interface between capture and visualization. Live mode is just "tail a file that something is appending to". This buys a few nice properties:

- Capture scripts and the viewer never talk to each other directly.
- A crash loses nothing, because the file is the recording.
- Replay is free. The same server endpoint replays the file, then streams new lines as they arrive.
- Supporting a new agent framework means writing one script that emits this schema.

## Event schema (the contract)

One JSON object per line, append-only:

```jsonc
{
  "id": "n7",                 // unique within the trail
  "parent_id": "n5",          // the step this one grew from; null for roots. This is what makes it a tree.
  "timestamp": "2026-07-06T10:00:17.500Z",
  "type": "prompt | thought | text | tool_call | tool_result |
           file_read | file_write | decision | backtrack | error | session",
  "label": "Read auth/config.py",   // short summary, shown next to the node
  "detail": "...full content...",   // shown in the side panel on click
  "status": "active | success | failed"
}
```

A few rules keep the stream simple:

- **Events are appended, never rewritten.** A tool call is emitted with `status: "active"`. The viewer flips it to success or failed when its result node arrives as a child.
- **Branches are implicit.** A node whose parent already has children is a fork.
- **Dead branches are derived, not declared.** When a new sibling appears at a fork, and an older sibling subtree contains a failure or a backtrack, that older subtree is rendered as an abandoned attempt and the new branch gets the pivot badge.
- An event with `type: "session"` carries the session title and is not rendered as a node.

## Claude Code capture notes

Claude Code writes session transcripts to `~/.claude/projects/<cwd-slug>/<session>.jsonl`. Each entry already has `uuid` and `parentUuid` fields, so the tree structure comes for free. The capture script projects those entries into trail events:

- assistant thinking, text, and tool_use blocks become thought, text, and call nodes (Read, Glob and Grep become `file_read`; Edit and Write become `file_write`)
- tool results attach as children of their call, and errors become `error` nodes
- parallel tool calls in one message fan out visibly from the same parent
- subagent runs (sidechains) hang off the Task call that spawned them

## Contributing

Capture layers for other agent frameworks are the most wanted contribution: one small script per framework makes the same viewer work for every agent tool. See [CONTRIBUTING.md](CONTRIBUTING.md) for the project layout, how to build a capture layer, and how to test changes. This project follows a [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE)
