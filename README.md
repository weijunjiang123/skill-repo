# Skill Repo

团队共享的 Code Agent Skill 管理工具。

通过 GitHub / GitLab 等远程 Git 仓库，在团队间共享和管理 Claude Code、Codex、Kiro 的 Skill。支持 macOS、Linux、Windows。

## 为什么需要它

Code Agent 的 Skill 散落在每个人的本地目录里，团队协作时面临几个问题：

- 好用的 Skill 无法方便地分享给同事
- 不同设备之间同步 Skill 很麻烦
- 没有统一的地方管理和发现可用的 Skill

Skill Repo 用一个 Git 仓库作为中心，让团队成员可以上传、下载、同步 Skill，就像管理代码一样。

## 功能

**远程仓库管理**
- 连接已有的 Skill 仓库（GitHub / GitLab，支持 HTTPS 和 SSH）
- 一键初始化空仓库为标准 Skill 仓库（自动创建目录结构、同步脚本、prek 配置）

**跨平台 Skill 安装**
- 从远程仓库安装 Skill 到本地 Claude Code / Codex / Kiro
- 支持按名称安装单个、批量安装全部
- Claude Code 平台自动同步 command 文件

**Skill 上传与共享**
- 从本地平台上传 Skill 到远程仓库
- 自动 git commit + push，支持指定分类
- 上传前自动验证 Skill 元数据完整性

**交互式 TUI**
- 菜单式操作，无需记忆命令参数
- 支持方向键导航、Space 多选、Esc 返回
- 美观的表格展示 Skill 概览

**自动化维护**
- 集成 prek（Git Hook 工具），提交时自动同步生成文件
- 自动维护 `skills/README.md` 目录、`commands/*.md`、`.claude-plugin/manifest.json`

## 安装

```bash
pip install skill-repo
```

或使用 uv：

```bash
uv tool install skill-repo
```

## 快速开始

### 1. 初始化一个新的 Skill 仓库

在 GitHub / GitLab 上创建一个空仓库，然后：

```bash
skill-repo init git@github.com:your-team/skills.git
```

这会自动创建标准目录结构并推送到远程。

### 2. 或者连接已有的 Skill 仓库

```bash
skill-repo connect git@github.com:your-team/skills.git
```

### 3. 安装 Skill 到本地

```bash
# 查看可用 Skill
skill-repo install --target claude --list

# 安装单个
skill-repo install --target kiro --skill my-skill

# 安装全部
skill-repo install --target claude --all
```

### 4. 上传本地 Skill 到仓库

```bash
# 查看本地 Skill
skill-repo upload --source kiro --list

# 上传到仓库
skill-repo upload --source kiro --skill my-skill --category tools
```

### 5. 交互式模式

不想记命令？直接进入交互式菜单：

```bash
skill-repo interactive
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `skill-repo connect <url>` | 连接远程 Skill 仓库 |
| `skill-repo init <url>` | 初始化空仓库为 Skill 仓库 |
| `skill-repo install` | 从仓库安装 Skill 到本地平台 |
| `skill-repo upload` | 上传本地 Skill 到仓库 |
| `skill-repo status` | 查看仓库状态和 Skill 概览 |
| `skill-repo config show` | 查看当前配置 |
| `skill-repo config set <key> <value>` | 修改配置 |
| `skill-repo prek setup` | 配置 prek Git Hook |
| `skill-repo prek scan` | 扫描仓库 Skill 并检查元数据 |
| `skill-repo interactive` | 进入交互式 TUI 模式 |

## 支持的平台

| 平台 | 本地路径 | 环境变量覆盖 |
|------|---------|-------------|
| Claude Code | `~/.claude/skills` | `CLAUDE_SKILLS_DIR` |
| Codex | `~/.codex/skills` | `CODEX_SKILLS_DIR` |
| Kiro | `~/.kiro/skills` | `KIRO_SKILLS_DIR` |

## Skill 仓库结构

初始化后的远程仓库结构：

```
your-skill-repo/
├── README.md                          # 项目说明（自动生成）
├── skills/                            # Skill 集合
│   ├── README.md                      # Skill 目录（自动维护）
│   ├── tools/                         # 分类目录
│   │   └── my-skill/
│   │       └── SKILL.md               # Skill 元数据 + 内容
│   └── workflow/
│       └── another-skill/
│           └── SKILL.md
├── commands/                          # Claude Code command 文件（自动生成）
├── .claude-plugin/manifest.json       # Claude marketplace 清单（自动生成）
├── scripts/                           # 同步脚本
├── prek.toml                          # Git Hook 配置
└── pyproject.toml
```

每个 Skill 是一个目录，必须包含 `SKILL.md` 文件：

```yaml
---
name: "my-skill"
description: "这个 Skill 做什么"
---

Skill 的详细说明和 prompt 内容...
```

## 配置

配置文件位置：
- Linux / macOS: `~/.config/skill-repo/config.toml`
- Windows: `%APPDATA%/skill-repo/config.toml`

支持的配置项：

| 键 | 说明 |
|----|------|
| `repo.url` | 已连接的远程仓库 URL |
| `repo.cache_path` | 本地缓存路径 |
| `defaults.target_platform` | 默认安装目标平台 |

## 开发

```bash
# 克隆项目
git clone <this-repo>
cd skill-repo

# 安装依赖
uv sync --group dev

# 运行测试
uv run pytest

# 本地运行 CLI
uv run skill-repo --help
```

## License

MIT
