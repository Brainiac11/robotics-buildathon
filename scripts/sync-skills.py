#!/usr/bin/env python3
"""Copy skills from .agents/skills/ (the source) to .claude/skills/.

.agents/skills/ is read by Codex, Cursor, Gemini CLI and Copilot; Claude Code reads
.claude/skills/. Copies are used instead of symlinks because symlinks break on Windows.

Skills marked `organizer: "true"` in their metadata get `disable-model-invocation: true` in the
Claude copy, so Claude Code only runs them when a person asks for them by name.

    python scripts/sync-skills.py           # write the copies
    python scripts/sync-skills.py --check   # exit 1 if they are out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".agents" / "skills", ROOT / ".claude" / "skills"


def claude_version(text: str) -> str:
    head, sep, body = text.partition("\n---\n")
    if sep and 'organizer: "true"' in head and "disable-model-invocation" not in head:
        head += "\ndisable-model-invocation: true"
    return head + sep + body


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for src in sorted(SRC.rglob("*")):
        if not src.is_file():
            continue
        dst = DST / src.relative_to(SRC)
        wanted = claude_version(src.read_text()) if src.name == "SKILL.md" else src.read_text()
        if not dst.exists() or dst.read_text() != wanted:
            stale.append(dst.relative_to(ROOT))
            if not check:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(wanted)
    for dst in sorted(DST.rglob("*")) if DST.exists() else []:
        if dst.is_file() and not (SRC / dst.relative_to(DST)).exists():
            stale.append(dst.relative_to(ROOT))
            if not check:
                dst.unlink()
    if check and stale:
        print("out of date (run scripts/sync-skills.py):", *stale, sep="\n  ")
        return 1
    print(f"{'checked' if check else 'synced'} {len(list(SRC.glob('*/SKILL.md')))} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
