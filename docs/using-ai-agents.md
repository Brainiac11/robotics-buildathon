# Working with an AI coding agent

This repo is set up so that coding agents (Claude Code, Cursor, Codex, Gemini CLI, Copilot)
can do useful work in it: they can read the rules, write an app, run it in the simulator, look
at what the robot saw, and iterate until the gate passes.

## What the repo gives your agent

| | Where | What it is for |
|---|---|---|
| Rules and a map of the repo | [AGENTS.md](../AGENTS.md) | Read automatically by most agents. Claude Code reads it through `CLAUDE.md` |
| Skills | `.agents/skills/` (and a copy in `.claude/skills/`) | Step-by-step know-how the agent loads when relevant |
| Reference | [api.md](api.md), [robot.md](robot.md), [cookbook.md](cookbook.md) | What the SDK and robot can do, with tested examples |
| Eyes | `robot snapshot`, `robot run --trace` | Camera frames and state written to files the agent can open |
| A judge | `robot sim-check` | A deterministic pass/fail with reasons the agent can act on |

The skills for participants:

- **write-behavior**: writing or changing an app with the SDK.
- **run-sim**: running, inspecting and gating an app in simulation.
- **offload-perception**: using a neural network or vision-language model with the robot.
- **debug-robot**: finding out why the simulator, an app or the robot is not doing what you expect.

## Getting good results

**Say what you want the robot to do, in physical terms, and how you will know it worked.**

> Make an app in `teams/rockets` that picks up the green cube in the `table` scene and puts it
> on the yellow pad. It must pass the gate. Show me where the cube ends up.

Requests like this have been tested against this repo with fresh agents that had no other
help: they produced working apps, passed the gate and reported the outcome from the gate's
result file.

Things that help:

- **Name the scene** (`table` by default, or `pick`). The wheels are off at the event.
- **Ask for evidence, not just a pass.** The gate only proves the app does not crash or break
  limits. Ask the agent to check the outcome from `.simcheck/<app>.json` (`final_truth` has
  the true position of every object) or from snapshots.
- **Ask it to look.** "Take a snapshot and tell me what the camera sees" catches a lot.
- **Have it test more than one case**: `robot sim-check <app> --seed 1`, `--seed 2`, ...
  moves the objects.
- **Keep it in your team directory.** The rules tell agents not to modify the SDK, the
  simulator or the safety limits to make an app pass.

## What your agent will not do, by design

- Run anything on, enable, or drive the real robot. Those are supervisor actions.
- Raise speed or joint limits, or switch off safety checks.
- Talk to the motors directly. Apps go through the SDK.

It can always stop the robot (`robot estop`).

## Using the real robot's data with your agent

After a slot, give the agent your app's output from the real run and ask what went wrong.
For vision tuning, ask the supervisor for real camera frames, then:

> These frames in `snapshots/real` are from the real camera. Adjust our colour thresholds so
> the red block is detected in all of them, and keep the simulator scene passing too.

## If your agent seems lost

- Point it at `AGENTS.md` and `docs/getting-started.md` explicitly.
- If it claims a feature exists and it does not work, check the "Current state" section of
  `AGENTS.md`: a few planned features are not built yet.
- If the simulator will not start for it, have it read the `debug-robot` skill, or start
  `robot sim` yourself in a terminal and let it use that one.
- Several simulators can run on one machine if each uses its own ports
  (`robot sim --port 5660 --dashboard-port 8081`, then `ROBOT_HOST=localhost:5660`).
