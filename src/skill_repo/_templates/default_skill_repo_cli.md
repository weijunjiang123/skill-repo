---
name: "skill-repo-cli"
description: "操作 skill-repo CLI 工具，管理团队共享的 Code Agent Skill（安装、上传、同步、配置）"
---

# Skill Repo CLI 操作指南

你是一个帮助用户操作 `skill-repo` CLI 工具的助手。skill-repo 用于通过 Git 仓库在团队间共享和管理 Claude Code / Codex / Kiro / Hermes Agent 的 Skill。

## 工具安装

如果用户尚未安装 skill-repo，使用以下方式安装：

```bash
# pip 安装
pip install git+https://github.com/weijunjiang123/skill-repo.git

# 或使用 uv
uv tool install git+https://github.com/weijunjiang123/skill-repo.git
```

安装后可通过 `skill-repo --help` 验证。

## 命令速查

### 仓库管理

| 命令 | 说明 |
|------|------|
| `skill-repo connect <git-url>` | 连接到已有的远程 Skill 仓库 |
| `skill-repo connect <git-url> --alias <name>` | 连接仓库并指定别名（多仓库） |
| `skill-repo init <git-url>` | 初始化空仓库为标准 Skill 仓库结构 |
| `skill-repo status` | 查看仓库连接状态和 Skill 概览 |

### Skill 操作

| 命令 | 说明 |
|------|------|
| `skill-repo install --target <platform> --list` | 列出仓库中可用的 Skill |
| `skill-repo install --target <platform> --skill <name>` | 安装指定 Skill |
| `skill-repo install --target <platform> --all` | 安装所有 Skill |
| `skill-repo install --target <platform> --skill <name> --from <alias>` | 从指定仓库安装 |
| `skill-repo search <keyword>` | 按名称/描述/分类搜索 Skill |
| `skill-repo search <keyword> --from <alias>` | 在指定仓库中搜索 |
| `skill-repo update --target <platform>` | 更新已安装的 Skill 到最新版本 |
| `skill-repo update --target <platform> --dry-run` | 仅检查哪些有更新，不实际更新 |
| `skill-repo remove --target <platform> --skill <name>` | 从本地平台卸载 Skill |
| `skill-repo diff --target <platform> --skill <name>` | 对比本地 vs 远程 Skill 差异 |
| `skill-repo create --name <name>` | 脚手架创建新 Skill（自动生成 SKILL.md） |
| `skill-repo create --name <name> --target <platform>` | 直接在平台目录创建 |
| `skill-repo upload --source <platform> --list` | 列出本地平台的 Skill |
| `skill-repo upload --source <platform> --skill <name> --category <cat>` | 上传 Skill 到仓库 |
| `skill-repo upload --source <platform> --skill <name> --no-push` | 仅本地提交不推送 |

`<platform>` 可选值：`claude`、`codex`、`kiro`、`hermes`

### 版本管理

| 命令 | 说明 |
|------|------|
| `skill-repo history --skill <name>` | 查看 Skill 的 Git 变更历史 |
| `skill-repo history --skill <name> --limit 50` | 显示更多历史记录 |
| `skill-repo rollback --skill <name> --to <commit>` | 将 Skill 回退到指定 Git 版本 |
| `skill-repo rollback --skill <name> --to <commit> --push` | 回退并推送到远程 |
| `skill-repo pin --skill <name> --target <platform>` | 安装当前 HEAD 版本（版本锁定） |
| `skill-repo pin --skill <name> --commit <hash> --target <platform>` | 安装指定历史版本 |

### 配置管理

| 命令 | 说明 |
|------|------|
| `skill-repo config show` | 查看当前所有配置 |
| `skill-repo config set <key> <value>` | 修改配置项 |

配置项：`repo.url`（仓库地址）、`repo.cache_path`（缓存路径）、`defaults.target_platform`（默认平台）

### prek 集成（Git Hook）

| 命令 | 说明 |
|------|------|
| `skill-repo prek setup` | 生成/更新 prek.toml 配置 |
| `skill-repo prek run` | 手动触发同步脚本 |
| `skill-repo prek scan` | 扫描仓库 Skill 并检查元数据完整性 |

### 交互式模式

```bash
skill-repo interactive
```

进入 TUI 菜单，支持方向键导航、Space 多选，无需记忆命令参数。

## 常见操作流程

### 首次使用：初始化新仓库

```bash
# 1. 在 GitHub/GitLab 创建空仓库后
skill-repo init git@github.com:your-team/skills.git

# 2. 上传本地已有的 Skill
skill-repo upload --source kiro --skill my-skill --category tools

# 3. 配置 Git Hook 自动同步
skill-repo prek setup
```

### 首次使用：连接已有仓库

```bash
# 1. 连接
skill-repo connect git@github.com:your-team/skills.git

# 2. 查看可用 Skill
skill-repo install --target kiro --list

# 3. 安装需要的 Skill
skill-repo install --target kiro --skill useful-skill
# 或安装全部
skill-repo install --target kiro --all
```

### 日常：分享 Skill 给团队

```bash
# 查看本地有哪些 Skill
skill-repo upload --source kiro --list

# 上传到仓库（自动 commit + push）
skill-repo upload --source kiro --skill my-new-skill --category workflow
```

### 日常：获取团队新 Skill

```bash
# 查看仓库有什么新的
skill-repo install --target kiro --list

# 安装
skill-repo install --target kiro --skill team-skill
```

## 平台本地路径

| 平台 | 默认路径 | 环境变量覆盖 |
|------|----------|-------------|
| Claude Code | `~/.claude/skills` | `CLAUDE_SKILLS_DIR` |
| Codex | `~/.codex/skills` | `CODEX_SKILLS_DIR` |
| Kiro | `~/.kiro/skills` | `KIRO_SKILLS_DIR` |
| Hermes Agent | `~/.hermes/skills` | `HERMES_SKILLS_DIR` |

## Skill 仓库结构

```
your-skill-repo/
├── skills/
│   ├── README.md              # 自动维护的目录
│   ├── tools/
│   │   └── my-skill/
│   │       └── SKILL.md       # 必须包含 name + description frontmatter
│   └── workflow/
│       └── another-skill/
│           └── SKILL.md
├── commands/                   # Claude Code command 文件（自动生成）
├── .claude-plugin/manifest.json
├── scripts/                    # 同步脚本
├── prek.toml                   # Git Hook 配置
└── pyproject.toml
```

## SKILL.md 格式

每个 Skill 必须包含 YAML frontmatter：

```markdown
---
name: "skill-name"
description: "这个 Skill 做什么"
version: "0.1.0"
author: "your-name"
updated: "2025-01-01"
---

Skill 的详细说明和 prompt 内容...
```

必填字段：`name`、`description`。可选字段：`version`、`author`、`updated`（列表展示时自动显示）。

上传前会自动验证 `name` 和 `description` 字段不为空。

## 注意事项

- 所有仓库操作（install/upload/status）前需先 `connect` 或 `init`
- `upload` 默认自动 commit + push，使用 `--no-push` 可仅本地提交
- `--category` 不指定时默认归入 `uncategorized`
- Git URL 支持 HTTPS 和 SSH 两种格式
- 使用 `skill-repo prek scan` 可批量检查所有 Skill 的元数据完整性
