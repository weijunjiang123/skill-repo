"""初始化仓库时使用的文件模板。"""

ROOT_README = """\
# Skill Repo

团队共享的 Code Agent Skill 仓库，支持 Claude Code / Codex / Kiro。

## 快速开始

### 安装 CLI 工具

```bash
pip install skill-repo
```

### 连接此仓库

```bash
skill-repo connect <本仓库 git URL>
```

### 安装 Skill 到本地

```bash
# 安装全部到 Claude Code
skill-repo install --target claude --all

# 安装单个到 Kiro
skill-repo install --target kiro --skill <name>

# 交互式模式
skill-repo interactive
```

### 上传 Skill 到仓库

```bash
skill-repo upload --source claude --skill <name>
```

## 目录结构

```
skills/           # Skill 集合（按分类组织）
commands/         # Claude Code command 文件（自动生成）
.claude-plugin/   # Claude marketplace manifest（自动生成）
scripts/          # 同步脚本
prek.toml         # Git hook 配置
```
"""

SKILLS_README = """\
# Skills

共享 skill 集合。

<!-- BEGIN AUTO SKILLS -->
<!-- END AUTO SKILLS -->
"""

PREK_TOML = """\
default_install_hook_types = ["post-commit"]
default_stages = ["post-commit"]

[[repos]]
repo = "local"
hooks = [
  { id = "sync-skills-artifacts", name = "Sync marketplace and skills README", entry = "python scripts/post_commit_sync.py", language = "system", pass_filenames = false, always_run = true, stages = ["post-commit"] },
]
"""

MANIFEST_JSON = """\
{
  "name": "skill-repo",
  "version": "1.0.0",
  "skills": []
}
"""

PYPROJECT_TOML = """\
[project]
name = "skill-repo"
version = "0.1.0"
description = "共享 Skill 仓库"
requires-python = ">=3.10"
"""

GITIGNORE = """\
__pycache__/
*.pyc
.venv/
*.egg-info/
.DS_Store
"""

POST_COMMIT_SYNC_PY = """\
#!/usr/bin/env python3
\"\"\"Post-commit sync: run sync generators.\"\"\"
import subprocess, sys, os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run(script):
    path = os.path.join(REPO_ROOT, "scripts", script)
    subprocess.check_call([sys.executable, path], cwd=REPO_ROOT)

def main():
    run("sync_claude_marketplace.py")
    run("sync_skills_readme.py")
    run("sync_commands.py")
    result = subprocess.run(
        ["git", "diff", "--quiet", "--",
         ".claude-plugin/manifest.json", "skills/README.md", "commands/"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("[prek] Updated generated files, include them in your next commit.")

if __name__ == "__main__":
    main()
"""

SYNC_COMMANDS_PY = '''\
#!/usr/bin/env python3
"""Sync commands/*.md from public skills/**/SKILL.md."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
COMMANDS_DIR = ROOT / "commands"
TEMPLATE = """---
description: {description}
location: plugin
---

Use the `{name}` skill to help with this task.
"""

def parse_frontmatter(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return p.parent.name, ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return p.parent.name, ""
    name, desc = p.parent.name, ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip(\\'"\\').strip("'")
        if k == "name":
            name = v or name
        elif k == "description":
            desc = v
    return name, desc

def main():
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    updated = 0
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = skill_md.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name, desc = parse_frontmatter(skill_md)
        if not desc:
            continue
        desired = TEMPLATE.format(name=name, description=desc)
        cmd_file = COMMANDS_DIR / f"{name}.md"
        if cmd_file.exists() and cmd_file.read_text(encoding="utf-8") == desired:
            continue
        cmd_file.write_text(desired, encoding="utf-8")
        updated += 1
    print(f"updated commands: {updated} files" if updated else "commands up to date")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
'''

SYNC_SKILLS_README_PY = '''\
#!/usr/bin/env python3
"""Sync skills catalog in skills/README.md."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
README = SKILLS_DIR / "README.md"
START = "<!-- BEGIN AUTO SKILLS -->"
END = "<!-- END AUTO SKILLS -->"

def parse_fm(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return p.parent.name, ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return p.parent.name, ""
    meta = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip(\\'"\\').strip("'")
    return meta.get("name", p.parent.name), meta.get("description", "")

def main():
    entries = []
    for sm in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = sm.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name, desc = parse_fm(sm)
        rp = sm.parent.relative_to(ROOT).as_posix()
        entries.append((name, desc, rp))
    lines = [START, "| Skill | Description | Path |", "| --- | --- | --- |"]
    for n, d, p in entries:
        lines.append(f"| `{n}` | {d} | [`{p}`](../{p}/SKILL.md) |")
    lines.append(END)
    gen = "\\n".join(lines)
    if not README.exists():
        README.write_text(gen + "\\n", encoding="utf-8")
        return
    content = README.read_text(encoding="utf-8")
    if START in content and END in content:
        s, e = content.index(START), content.index(END) + len(END)
        updated = content[:s] + gen + content[e:]
    else:
        updated = content.rstrip() + "\\n\\n" + gen + "\\n"
    if updated != content:
        README.write_text(updated, encoding="utf-8")
        print("updated skills README")
    else:
        print("skills README up to date")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
'''

SYNC_CLAUDE_MARKETPLACE_PY = '''\
#!/usr/bin/env python3
"""Sync .claude-plugin/manifest.json from skills."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "manifest.json"
SKILLS_DIR = ROOT / "skills"

def parse_name(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip() == "name":
            return v.strip().strip(\\'"\\').strip("'")
    return ""

def main():
    entries = []
    for sf in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = sf.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name = parse_name(sf) or sf.parent.name
        rp = sf.parent.relative_to(ROOT).as_posix()
        cat = rel[0] if len(rel) > 1 else ""
        e = {"name": name, "path": rp, "command": f"commands/{name}.md", "tested": False}
        if cat:
            e["category"] = cat
        entries.append(e)
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if data.get("skills") == entries:
        print("manifest up to date")
        return
    data["skills"] = entries
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(f"updated manifest: {len(entries)} entries")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
'''
