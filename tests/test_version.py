from pathlib import Path

import tomli

import skill_repo


def test_package_version_matches_project_metadata():
    repo_root = Path(__file__).resolve().parents[1]
    pyproject_path = repo_root / "pyproject.toml"
    pyproject = tomli.loads(pyproject_path.read_text(encoding="utf-8"))

    assert skill_repo.__version__ == pyproject["project"]["version"]


def test_lockfile_version_matches_project_metadata():
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomli.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    lockfile = tomli.loads((repo_root / "uv.lock").read_text(encoding="utf-8"))

    package = next(pkg for pkg in lockfile["package"] if pkg["name"] == "skill-repo")
    assert package["version"] == pyproject["project"]["version"]
