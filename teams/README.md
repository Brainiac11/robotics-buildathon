# Team code

One directory per team. This is the only place you need to change.

```bash
cp -r apps/_template teams/<your-team>
uv run robot run teams/<your-team>            # with `uv run robot sim` running
uv run robot sim-check teams/<your-team>      # the gate
```

## What goes in your directory

| File | Required | Purpose |
|---|---|---|
| `main.py` | yes | Your app. It is started with `python main.py` from inside this directory |
| `app.yaml` | recommended | Tells the gate and the organizers how to run it (below) |
| `requirements.txt` | if needed | Extra Python packages, one per line. Installed automatically by `robot run`, `robot sim-check`, Docker, and on the robot |
| anything else | optional | More Python files, small data files, a README for your team |

`app.yaml`:

```yaml
needs_base: false    # true only if your team was granted the wheels (they are off by default)
scene: table         # simulator scene for the gate: table | pick | empty | targets
duration_s: 30       # how many simulated seconds the gate runs your app
```

Keep large files (model weights, datasets, recordings) out of git. On the real arm your app
runs on the supervisor's laptop: print what you want to keep, because its output is what you
get back.

## Rules

- Talk to the robot only through the `buildathon` SDK.
- Pass the gate, and show your team engineer it working, before your testing slot.
- Your app must not depend on changes outside your directory: only your directory goes to the
  robot. Editing other files locally to experiment is fine. If something in the SDK or
  simulator looks wrong, tell an organizer.

Start with [docs/getting-started.md](../docs/getting-started.md).
