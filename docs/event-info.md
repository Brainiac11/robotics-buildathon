# Event information

**Robotics Build-A-Thon** | SLABS × Silicon Hills, Austin | Fri Nov 13 – Sun Nov 15, 2026

Teams program an SO-101 robot arm: build in simulation, test on the real arm on Saturday, demo
on Sunday. Projects are open: each team builds whatever it wants with the arm.

**Organizers still need to fill in the lines marked TODO.**

| | |
|---|---|
| Repository | <https://github.com/Brainiac11/robotics-buildathon> (private: send Saathvik your GitHub username to be added) |
| Group chat | TODO |
| Wi-Fi at the house | TODO |
| Testing sign-up sheet | TODO (link) |

## Who to ask

| For | Ask |
|---|---|
| Your project, code, approach | Your team's engineer |
| Laptop setup, the simulator, this repo | Saathvik |
| The real arm, testing slots, props for your project | Sol |
| Anything about the event or the house | Shayan or Tanay |

## Schedule

You are in the house only for scheduled moments: check-in and intros, your testing slots, and
demos. Building happens off-site.

**Friday, Nov 13**

| Time | What |
|---|---|
| 6:00 – 7:00 PM | Check-in (bring your UT ID) |
| 7:00 – 7:30 | Welcome and overview |
| 7:30 – 8:15 | Technical intro: the arm, the simulator, what "ready for the arm" means |
| 8:15 – 9:00 | Teams pick a project, set a Saturday-morning simulation milestone, pencil in testing slots |
| 9:00 PM | House closes. Build off-site overnight |

**Saturday, Nov 14**

| Time | What |
|---|---|
| Morning | Build off-site. Your team engineer checks in on the group chat |
| 11:00 AM – 1:00 PM | **Sim sign-off**: show your team engineer your project working in the simulator; they mark you "ready" on the sign-up sheet |
| 1:00 – 7:00 PM | **Real-arm testing**: 30-minute slots, ready teams only |
| 7:00 – 8:00 PM | Open slots for re-runs, first come, first served |
| 8:00 PM | House closes |

**Sunday, Nov 15**

| Time | What |
|---|---|
| 8:00 – 8:50 AM | Last testing: about 10 minutes per team, in demo order |
| 9:00 – 10:00 | **Demos**: about 8 minutes per team |
| 10:00 – 10:30 | Wrap-up and group photo |

Meals: pizza on Friday; drinks and chips all weekend; you are on your own for meals on Saturday.

## What "ready for the arm" means

1. `uv run robot sim-check teams/<your-team>` prints **PASS**.
2. Your team engineer has watched it do what you intend in the simulator.

Details and how a testing slot runs: [robot-day.md](robot-day.md).

## Demo format

1. Two minutes: what you built and how.
2. Four minutes: live runs on the arm.
3. Two minutes: questions.

If a live run fails, you show your simulation or a clip from Saturday, then get one more
attempt if time allows. So record your good runs on Saturday.

## House rules

- You are in the house only during scheduled times, and nobody sleeps there.
- The door code is never shared. An organizer lets you in.
- Food and drinks stay in the kitchen, away from the arm and laptops.
- Respect the residents: keep it quiet, and stay out of rooms that are not ours.

## Arm safety

- The arm stays clamped inside the taped zone. Stay outside the tape while it is powered,
  unless you are the one operating in your slot.
- A supervisor is present whenever it is powered. Unplugging it is the kill switch.
- One operator at a time. First runs are at reduced speed.
- If anything binds or moves wrong, say "stop". Anyone can press STOP on the dashboard.

## Submitting your code

1. Work in `teams/<your-team>/` on a branch named after your team.
2. Commit and push it to the repository above.
3. Tell the supervisor the branch and commit at the start of your slot.

Only your team's directory is run on the arm.

## Before Friday night is over

- Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run `uv sync` in
  the repo (about 300 MB), or install Docker and run
  `docker compose -f docker/compose.sim.yaml build`.
- Run through [getting-started.md](getting-started.md) once while people are around to help.
