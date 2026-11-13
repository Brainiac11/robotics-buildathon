# Simulation assets

`so101/` is the SO-101 arm model from MuJoCo Menagerie
(<https://github.com/google-deepmind/mujoco_menagerie>, directory `robotstudio_so101`),
copied unmodified at the commit recorded in `so101/UPSTREAM_COMMIT`. It is licensed under
Apache-2.0 (`so101/LICENSE`).

The base, camera mount and scenes are generated at run time from `config/robot.yaml` and
`config/scenes/` by `packages/host/buildathon_host/backends/mujoco_sim.py`.
