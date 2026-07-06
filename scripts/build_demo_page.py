#!/usr/bin/env python3
"""Build the static GitHub Pages demo: the viewer with trail events embedded.

Reads viewer/index.html and one or more trail files, and writes a single
self-contained docs/index.html that needs no server. The viewer itself is not
modified; a small shim embedded in the page replays the bundled events through
the same fetch/EventSource surface the server would provide.

Usage: build_demo_page.py [trail.jsonl ...]   (defaults to trails/demo.trail.jsonl)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(ROOT, "viewer", "index.html")
OUT = os.path.join(ROOT, "docs", "index.html")

SHIM = """<script>
/* Static demo shim: serve bundled events through the same fetch/EventSource
   surface the server provides, so the unmodified viewer works from a file. */
const EMBED = %s;
window.EventSource = class {
  constructor(url) {
    const name = decodeURIComponent(url.split("/").pop());
    setTimeout(() => {
      for (const ev of EMBED[name] || []) this.onmessage && this.onmessage({ data: JSON.stringify(ev) });
    }, 0);
  }
  close() {}
};
window.fetch = async (url) => {
  if (String(url).endsWith("/api/sessions"))
    return { ok: true, json: async () => Object.keys(EMBED).map((n) => (
      { name: n, size: JSON.stringify(EMBED[n]).length, mtime: 1751800000, live: false })) };
  return { ok: false, json: async () => ({}) };
};
</script>
"""

GITHUB_LINK = ('<div class="sub" style="border-bottom:none;padding-top:8px">'
               '<a href="https://github.com/sudhanshutech/agent-trail" '
               'style="color:var(--teal);text-decoration:none">github.com/sudhanshutech/agent-trail</a></div>')


def main():
    paths = sys.argv[1:] or [os.path.join(ROOT, "trails", "demo.trail.jsonl")]
    embed = {}
    for p in paths:
        name = os.path.basename(p)
        with open(p) as f:
            embed[name] = [json.loads(line) for line in f if line.strip()]
    html = open(VIEWER).read()
    html = html.replace("<script>\n", SHIM % json.dumps(embed) + "<script>\n", 1)
    html = html.replace('<div class="sub">reasoning trails, live &amp; replayable</div>',
                        '<div class="sub">reasoning trails, live &amp; replayable</div>' + GITHUB_LINK, 1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print("wrote %s (%d sessions, %.1f kb)" % (OUT, len(embed), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
