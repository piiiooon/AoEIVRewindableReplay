#!/usr/bin/env python3
"""PostToolUse hook for the Write tool.

When Claude creates a new file that INDEX.md does not mention, send Claude a
one-line reminder to add it. Prints nothing (and costs no tokens) otherwise.
"""
import json
import os
import sys

SKIP_PREFIXES = (".git/", ".claude/")
SKIP_FILES = ("INDEX.md",)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return

    if event.get("tool_name") != "Write":
        return

    response = event.get("tool_response")
    if isinstance(response, dict) and response.get("type") not in (None, "create"):
        return  # an existing file was overwritten, not created

    file_path = (event.get("tool_input") or {}).get("file_path")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd")
    if not file_path or not project:
        return

    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project))
    rel = rel.replace(os.sep, "/")
    if rel.startswith("..") or rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES):
        return

    try:
        with open(os.path.join(project, "INDEX.md"), encoding="utf-8") as fh:
            index = fh.read()
    except OSError:
        return

    # Listed directly, or inside a folder that is listed (e.g. `docs/decisions/`).
    parts = rel.split("/")
    folders = ["/".join(parts[:i]) + "/" for i in range(1, len(parts))]
    if any(f"`{name}`" in index for name in [rel, *folders]):
        return

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"New file {rel} is not in INDEX.md. If its purpose is not "
                "clear from its name, add one line: path, then purpose."
            ),
        }
    }))


if __name__ == "__main__":
    main()
