#!/usr/bin/env python3
"""Post-commit sync: run marketplace and skills README generators.

Works on both Windows (python) and macOS/Linux (python3).
"""
import subprocess
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(script: str) -> None:
    path = os.path.join(REPO_ROOT, "scripts", script)
    subprocess.check_call([sys.executable, path], cwd=REPO_ROOT)


def main() -> None:
    run("sync_claude_marketplace.py")
    run("sync_skills_readme.py")
    run("sync_commands.py")

    result = subprocess.run(
        ["git", "diff", "--quiet", "--",
         ".claude-plugin/manifest.json", "skills/README.md", "commands/"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("[prek] Updated generated files:")
        print("  - .claude-plugin/manifest.json")
        print("  - skills/README.md")
        print("  - commands/*.md")
        print("[prek] Please include them in your next commit.")


if __name__ == "__main__":
    main()
