# Your time on the real arm

There is one arm and every team needs it, so arm time is short. This page is how to arrive
ready and leave with something useful. The schedule is in [event-info.md](event-info.md).

A supervisor runs the arm. Your code runs on the laptop the arm is plugged into; you do not
connect your own laptop to it.

> The arm's hardware was brought up just before the event. Details here may change; your team
> engineer and the supervisor will tell you if they do.

## 1. Sim sign-off (Saturday 11 AM – 1 PM)

Only "ready" teams get a testing slot. To be marked ready, show your team engineer:

- [ ] `uv run robot sim-check teams/<your-team>` printing **PASS**, with no warnings you
      cannot explain.
- [ ] Your project doing what you intend in the simulator (dashboard, or a `--trace`).
- [ ] The same in safe mode: `uv run robot sim --safe-mode`. Half speed changes timing.
- [ ] Your team directory committed and pushed, and you know the branch and commit.

Also worth doing before your slot:

- [ ] Your app prints what it is doing at each stage. Its output is the main thing you get
      back from a run.
- [ ] If you have a `requirements.txt`, tell the supervisor at the start: the packages are
      downloaded on the arm laptop the first time, which takes a moment and needs internet.
- [ ] Any props your project needs are cleared with Sol.
- [ ] You know the one thing you want to learn from this slot.

## 2. Your testing slot (30 minutes)

1. Arrive 5 minutes early. Everyone not in your team stays out of the arm area.
2. The supervisor pulls your code onto the arm laptop and runs the gate again.
3. **First run at reduced speed** (safe mode: joints at half speed). If anything binds or
   moves wrong, the supervisor cuts power.
4. Full-speed runs of your project, as many as fit.
5. Clear the station for the next team.
6. The supervisor logs a one-line note: what ran, what broke.

What to expect:

| | |
|---|---|
| **Time limit** | About 3 minutes per run; then the arm stops and holds. Ask for another run |
| **Starting pose** | The arm starts wherever the last run left it. Move to a known pose (`robot.arm.move_to("home")`) at the start of your app |
| **Your output** | Shown on the arm laptop's screen as it runs and saved to a file. Stand where you can read it; ask for the file afterwards |
| **Stopping** | Say "stop": the supervisor presses Ctrl-C. Unplugging the arm is the kill switch |
| **Motion blocked** | Between runs the arm will not move for anyone. That is normal |

Record your good runs on video: if your live demo fails on Sunday, a Saturday clip is your
fallback.

## 3. Sunday

- **8:00 – 8:50 AM:** about 10 minutes per team for a last check, in demo order.
- **9:00 – 10:00:** demos, 8 minutes per team: 2 to explain, 4 of live runs, 2 of questions.

## What usually goes wrong the first time

| On the real arm | Why | What to do |
|---|---|---|
| The gripper misses by a centimetre or two | Real joints sag and have slack; the real arm's zero positions differ slightly from the simulator's | Approach from above, open wide, close with `gripper.close(wait=True)` and check the result. Adjust your angles on the real arm, not in the simulator |
| It does not see the object | Real colours and lighting differ; the real camera is not exactly where the simulator's is | Tune thresholds on real frames (below). Do not hard-code pixel positions from the simulator |
| An object is not where the simulator had it | The table layout is whatever is on the table | Bring or place your own props; measure positions on the real table |
| The arm moves slowly | Safe mode on a first run | Expected |
| It stops partway | Time limit, the supervisor stopped it, or a joint reached its limit | Read your output; ask the supervisor |
| A joint moves the opposite way to the simulator | The real arm's calibration | Tell the supervisor; this is theirs to fix |

The safest designs **sense, then act**: look for the object, decide, move, and check the
result (the gripper reading, another camera frame) instead of replaying fixed angles blind.

## Real camera frames for tuning

The simulator's colours are not the real camera's. During your slot, ask the supervisor to run

```bash
uv run robot snapshot --out snapshots/<your-team>
```

and send you the pictures. Tune your thresholds on them with "Find the right colour
thresholds" in the [cookbook](cookbook.md), then re-run the gate.

## After your slot

- Read your app's output before changing anything.
- Reproduce the problem in the simulator if you can, fix it, pass the gate again, and take an
  open slot (Saturday 7–8 PM) or use your Sunday morning check.

## If your project needs a GPU or a large model

It cannot run on the arm laptop as-is. Talk to your team engineer and Saathvik early, before
your slot: see [offload.md](offload.md).
