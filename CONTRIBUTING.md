# Contributing to agent-trail

Thanks for your interest in making agent reasoning visually legible. Contributions of every size are welcome: capture layers for new agent frameworks, viewer improvements, bug reports, docs fixes, and sample trails that show interesting reasoning shapes.

## Ground rules

- **Zero runtime dependencies.** The server and capture scripts use only the Python standard library, and the viewer is a single self-contained HTML page. This is a deliberate design choice so anyone can clone and run the project in seconds. Please do not add package managers, build steps, or CDN scripts. If a change truly needs a dependency, open an issue first so we can discuss it.
- **The trail file is the contract.** Capture layers and the viewer only communicate through append-only trail JSONL files (the schema is documented in the README). Changes to the schema affect every capture layer, so propose them in an issue before writing code.
- **Events are appended, never rewritten.** Derived state (statuses, dead branches, pivots) belongs in the viewer, not the capture layer.
- Be kind. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

There is nothing to install. Clone the repo and run:

```bash
python3 server.py
```

Open http://127.0.0.1:7845 and click **demo**. Any Python 3.8+ and a modern browser should work.

## Project layout

```
server.py                 HTTP + SSE server, Python standard library only
viewer/index.html         the renderer, a single self-contained page with no dependencies
capture/claude_code.py    Claude Code transcript to trail events
samples/demo.trail.jsonl  hand-written branching session used by the demo
trails/                   captured sessions live here (gitignored except the demo)
```

## Adding a capture layer for another framework

This is the most valuable kind of contribution. The goal is one script per framework that emits the trail schema, so the same viewer works for every agent tool.

The whole integration is: emit the schema described in the README, one JSON object per line, appended to a file in `trails/`. For most frameworks it is about 50 lines:

1. Subscribe to whatever event stream the framework exposes: callbacks, a log file you can tail, hook points, or OTel spans.
2. Map each event to a node with a stable `id` and a `parent_id`. The parent link is what makes the trail a tree instead of a list.
3. Keep `label` short (it is drawn next to the node) and put the full payload in `detail`.
4. Emit tool calls with `status: "active"` and let their result node close them. Never rewrite a line you already wrote.

Conventions to follow, matching the Claude Code capture layer:

- map file reads and searches to `file_read`, and edits or writes to `file_write`, so the viewer colors them consistently
- attach tool results as children of the call that produced them, and use type `error` with `status: "failed"` for failed calls
- if the framework runs subagents, hang their events off the node that spawned them
- emit one `type: "session"` event carrying a human-readable session title

Put the script in `capture/<framework>.py` (or another language if the framework demands it), give it a `--follow` flag for live tailing and an `--out` flag for the target trail file, and add a short usage note to the README.

## Testing your changes

CI runs these checks on every PR, and you can run them locally first:

```bash
# schema validation of the bundled trail data
python3 tests/validate_trail.py samples/demo.trail.jsonl trails/demo.trail.jsonl

# capture layer smoke test against the fixture transcript
python3 tests/capture_smoke.py

# render the demo trail in a real headless browser and assert it draws
# (test-only dependency, never shipped: npm i puppeteer-core)
CHROME_PATH=/path/to/chrome node tests/browser_smoke.mjs
```

If you add a capture layer, add a small sanitized fixture under `tests/fixtures/` and a smoke test like `tests/capture_smoke.py`, and run your new trail file through `tests/validate_trail.py`.

Please also verify by hand before opening a PR:

1. `python3 server.py` starts cleanly and the **demo** trail renders with a grayed-out dead branch and a pivot badge.
2. Replay works: scrub, step, and play at a couple of speeds.
3. Live mode works: append a line to a trail file while it is open in the viewer and confirm the node appears within a second.

```bash
echo '{"id":"t1","parent_id":"n23","timestamp":"2026-01-01T00:00:00Z","type":"thought","label":"live test","detail":"","status":"active"}' >> trails/demo.trail.jsonl
```

(Remember to `git checkout trails/demo.trail.jsonl` afterwards.)

For capture layer changes, also run your script against a real session of the target framework and check the tree has no orphaned `parent_id` references.

## Pull requests

- Keep PRs focused on one change.
- Describe what the change looks like in the viewer. Screenshots or short recordings help a lot, since the rendered trail is the product.
- Plain, human-readable writing in docs and UI strings, please.

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
