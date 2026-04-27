# Skill Repo

团队共享的 Code Agent Skill 仓库，支持 Claude Code / Codex / Kiro / Hermes Agent。

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

# 安装单个到 Hermes Agent
skill-repo install --target hermes --skill <name>

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
