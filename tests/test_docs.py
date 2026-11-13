"""Keep the docs honest: every recipe in docs/cookbook.md must pass the gate, and every
relative link in the participant docs must point at a file that exists."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RECIPE = re.compile(r"```python\n(# recipe: (?P<name>[\w-]+) \| scene: (?P<scene>\w+)(?P<flags>[^\n]*)\n.*?)```", re.S)
# A recipe's first line: "# recipe: <name> | scene: <scene>" plus, for wheel recipes,
# "| base: on" and optionally "| camera: base_front". Everything else runs arm-only.
RECIPES = [
    (m["name"], m["scene"], "base: on" in m["flags"], (re.search(r"camera: (\w+)", m["flags"]) or ["", ""])[1], m[1])
    for m in RECIPE.finditer((ROOT / "docs" / "cookbook.md").read_text())
]
DOCS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    *sorted((ROOT / "docs").glob("*.md")),
    ROOT / "apps" / "README.md",
    ROOT / "teams" / "README.md",
]


def test_cookbook_has_recipes():
    assert len(RECIPES) >= 12


@pytest.mark.parametrize(("name", "scene", "base", "camera", "code"), RECIPES, ids=[r[0] for r in RECIPES])
def test_cookbook_recipe_passes_the_gate(name, scene, base, camera, code, tmp_path, monkeypatch):
    pytest.importorskip("mujoco")
    from buildathon_cli.apps import find_app
    from buildathon_cli.simcheck import sim_check

    app = tmp_path / name
    app.mkdir()
    (app / "main.py").write_text(code)
    manifest = f"scene: {scene}\nduration_s: 40\nneeds_base: {'true' if base else 'false'}\n"
    (app / "app.yaml").write_text(manifest + (f"camera: {camera}\n" if camera else ""))
    monkeypatch.chdir(tmp_path)
    result = sim_check(find_app(str(app)))
    if result == 2:
        pytest.skip("the simulator could not start here (no OpenGL for rendering)")
    log = (tmp_path / ".simcheck" / f"{name}.log").read_text()
    assert result == 0, f"recipe {name} failed the gate:\n{log}"
    assert "Traceback" not in log
    assert "gave up" not in log and "not in view" not in log and "TIMED OUT" not in log, log


@pytest.mark.parametrize("doc", DOCS, ids=[str(d.relative_to(ROOT)) for d in DOCS])
def test_relative_links_resolve(doc):
    text = re.sub(r"```.*?```", "", doc.read_text(), flags=re.S)  # ignore code blocks
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (doc.parent / target.split("#")[0]).resolve()
        assert path.exists(), f"{doc.relative_to(ROOT)} links to {target}, which does not exist"
