<div align="center">

# 🧰 Skill Repo

**把团队的 Code Agent Skill 管起来**

用一个 Git 仓库，搞定 Claude Code / Codex / Kiro 的 Skill 共享、同步和版本管理。

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()

[快速开始](#-快速开始) · [功能](#-功能一览) · [命令参考](#-命令参考) · [开发](#-开发)

</div>

---

## 😩 痛点

你有没有遇到过这些情况：

- 写了个好用的 Skill，想分享给同事，只能手动拷贝目录
- 换了台电脑，之前调好的 Skill 全没了
- 团队里谁有什么 Skill、哪个版本，完全是黑盒
- 多个人改同一个 Skill，互相覆盖

Skill Repo 就是来解决这些问题的。

## 💡 思路

很简单 —— 用一个 Git 仓库当 Skill 的中心仓库，配一个 CLI 工具来操作。上传、安装、同步、版本管理，全部自动化。不需要懂 Git，不需要记命令，有交互式菜单。

```
你的 Skill ──上传──→ Git 仓库 ──安装──→ 同事的 Skill
                        ↑
                    版本管理、搜索、同步
```

## 🚀 快速开始

**安装**（需要 Python 3.8+ 和 Git）

用 pipx 安装（不会污染环境）

```bash
pip install pipx

pipx install git+https://github.com/weijunjiang123/skill-repo.git
```
安装完成后直接可用：

``` bash
skill-repo interactive
````

**30 秒上手**

```bash
# 1. 连接团队的 Skill 仓库
skill-repo connect git@github.com:your-team/skills.git

# 2. 看看有什么 Skill
skill-repo install --target kiro --list

# 3. 装一个试试
skill-repo install --target kiro --skill code-review

# 4. 把自己的 Skill 分享出去
skill-repo upload --source kiro --skill my-skill --category tools
```

**不想记命令？**

```bash
skill-repo interactive
```

进入交互式菜单，方向键选择，Space 多选，全程引导。

## ✨ 功能一览

<table>
<tr>
<td width="50%">

### 📥 安装 & 上传
从仓库安装 Skill 到本地，或把本地 Skill 上传共享。支持单个、批量、按分类。上传后自动生成 README 和 manifest。

### 🔍 搜索
按名称、描述、分类模糊搜索。支持同时搜本地和远程。搜到了可以直接安装。

### 🔄 更新 & 同步
一键检查哪些 Skill 有新版本，选择性更新。支持 `--dry-run` 先看看再说。

</td>
<td width="50%">

### 📜 版本管理
每次上传自动记录变更历史。可以查看谁在什么时候改了什么，回退到任意版本，锁定安装指定版本。

### 🌿 分支协作
多人场景下，上传自动走个人分支，无冲突时自动合并。有冲突提示创建 PR，不会搞坏主分支。

### 🖥️ 多平台 & 多仓库
同时管理 Claude Code、Codex、Kiro 三个平台。可以连接多个仓库（公司 + 社区），通过别名区分。

</td>
</tr>
</table>

## 📖 命令参考

<details>
<summary><b>仓库管理</b></summary>

```bash
skill-repo connect <git-url>              # 连接远程仓库
skill-repo connect <git-url> --alias team # 多仓库场景，指定别名
skill-repo init <git-url>                 # 初始化空仓库
skill-repo status                         # 查看仓库状态
```

</details>

<details>
<summary><b>Skill 操作</b></summary>

```bash
skill-repo install --target kiro --list           # 列出可用 Skill
skill-repo install --target kiro --skill <name>    # 安装单个
skill-repo install --target kiro --all             # 安装全部
skill-repo upload --source kiro --skill <name>     # 上传到仓库
skill-repo search <keyword>                        # 搜索
skill-repo update --target kiro                    # 更新已安装的
skill-repo update --target kiro --dry-run          # 只看不动
skill-repo remove --target kiro --skill <name>     # 卸载
skill-repo diff --target kiro --skill <name>       # 对比差异
skill-repo create --name <name>                    # 创建新 Skill 脚手架
```

</details>

<details>
<summary><b>版本管理</b></summary>

```bash
skill-repo history --skill <name>                          # 查看变更历史
skill-repo rollback --skill <name> --to <commit> --push    # 回退版本
skill-repo pin --skill <name> --commit <hash> --target kiro # 安装指定版本
```

</details>

<details>
<summary><b>协作 & 配置</b></summary>

```bash
skill-repo branch mode branch             # 切换到分支协作模式
skill-repo branch list                    # 查看待合并分支
skill-repo branch merge <branch-name>     # 合并分支
skill-repo config set defaults.target_platform kiro  # 设置默认平台
skill-repo interactive                    # 交互式 TUI（设置页面里也能改配置）
```

</details>

## 🏗️ Skill 仓库长什么样

```
your-skill-repo/
├── skills/
│   ├── README.md                  ← 自动生成的 Skill 目录
│   ├── tools/
│   │   └── code-review/
│   │       └── SKILL.md
│   └── workflow/
│       └── deploy-helper/
│           └── SKILL.md
├── commands/                       ← Claude Code command（自动生成）
├── .claude-plugin/manifest.json    ← Claude marketplace 清单（自动生成）
├── scripts/                        ← 同步脚本（给 prek 用）
└── prek.toml
```

每个 Skill 就是一个目录 + 一个 `SKILL.md`：

```markdown
---
name: "code-review"
description: "代码审查助手，自动检查常见问题并给出修改建议"
version: "0.2.0"
author: "alice"
updated: "2025-03-15"
---

你是一个代码审查助手...
```

## 🖥️ 支持的平台

| 平台 | 本地路径 | 环境变量覆盖 |
|:-----|:---------|:-------------|
| Claude Code | `~/.claude/skills` | `CLAUDE_SKILLS_DIR` |
| Codex | `~/.codex/skills` | `CODEX_SKILLS_DIR` |
| Kiro | `~/.kiro/skills` | `KIRO_SKILLS_DIR` |

## 🛠️ 开发

```bash
git clone https://github.com/weijunjiang123/skill-repo.git
cd skill-repo
uv sync --group dev
uv run pytest          # 跑测试
uv run skill-repo --help  # 本地运行
```

项目结构：

```
src/skill_repo/
├── cli.py              # CLI 命令（rich-click）
├── interactive.py      # 交互式 TUI（questionary + rich）
├── git_manager.py      # Git 操作（调用系统 git，不用 gitpython）
├── skill_manager.py    # Skill 发现、安装、同步
├── config_manager.py   # TOML 配置
├── metadata.py         # SKILL.md 解析
├── platforms.py        # 平台路径
├── _console.py         # 终端输出组件
└── _templates/         # 仓库初始化模板（独立文件，方便改）
```

几个开发时需要注意的点：

- 调用系统 `git` 而非 gitpython，用户本地的 SSH key 和 credential helper 直接能用
- `_templates/` 是独立文件不是 Python 字符串，改模板直接编辑文件就行
- 上传后的同步（README、commands、manifest）内置在 `SkillManager.sync_all()` 里，不依赖外部脚本
- Windows 上 `shutil.rmtree` 不能处理符号链接，`remove_skill` 已做兼容
- 测试用 pytest + hypothesis

## 📄 License

MIT

---

<div align="center">

如果觉得有用，给个 ⭐ 吧

</div>
