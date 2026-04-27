#!/usr/bin/env sh
set -eu

REPO="${SKILL_REPO_RELEASE_REPO:-weijunjiang123/skill-repo}"
VERSION="${SKILL_REPO_VERSION:-latest}"
BIN_NAME="${SKILL_REPO_BIN_NAME:-skill-repo}"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少依赖: $1" >&2
    exit 1
  fi
}

detect_asset() {
  os="$(uname -s)"
  arch="$(uname -m)"

  case "$os" in
    Darwin) os_slug="macos" ;;
    Linux) os_slug="linux" ;;
    *) echo "暂不支持当前系统: $os" >&2; exit 1 ;;
  esac

  case "$arch" in
    x86_64|amd64) arch_slug="x64" ;;
    arm64|aarch64) arch_slug="arm64" ;;
    *) echo "暂不支持当前 CPU 架构: $arch" >&2; exit 1 ;;
  esac

  printf 'skill-repo-%s-%s' "$os_slug" "$arch_slug"
}

choose_install_dir() {
  if [ -n "${SKILL_REPO_INSTALL_DIR:-}" ]; then
    printf '%s' "$SKILL_REPO_INSTALL_DIR"
    return
  fi

  if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    printf '%s' "/usr/local/bin"
    return
  fi

  printf '%s' "$HOME/.local/bin"
}

release_api_url() {
  if [ "$VERSION" = "latest" ]; then
    printf 'https://api.github.com/repos/%s/releases/latest' "$REPO"
  else
    printf 'https://api.github.com/repos/%s/releases/tags/%s' "$REPO" "$VERSION"
  fi
}

ensure_path_hint() {
  install_dir="$1"
  case ":$PATH:" in
    *":$install_dir:"*) return ;;
  esac

  if [ "${SKILL_REPO_MODIFY_PATH:-1}" = "0" ]; then
    echo "提示: $install_dir 不在 PATH 中。请手动加入 PATH 后使用 skill-repo。"
    return
  fi

  profile="${PROFILE:-}"
  if [ -z "$profile" ]; then
    case "${SHELL:-}" in
      */zsh) profile="$HOME/.zshrc" ;;
      */bash) profile="$HOME/.bashrc" ;;
      *) profile="$HOME/.profile" ;;
    esac
  fi

  touch "$profile"
  if ! grep -qs "skill-repo installer" "$profile"; then
    {
      echo ""
      echo "# skill-repo installer"
      echo "export PATH=\"$install_dir:\$PATH\""
    } >> "$profile"
  fi

  echo "已把 $install_dir 写入 $profile；重新打开终端后可直接运行 skill-repo。"
}

need curl

asset="$(detect_asset)"
install_dir="$(choose_install_dir)"
api_url="$(release_api_url)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT INT TERM

mkdir -p "$install_dir"
if [ ! -w "$install_dir" ]; then
  echo "安装目录不可写: $install_dir" >&2
  echo "可设置 SKILL_REPO_INSTALL_DIR 指定其他目录。" >&2
  exit 1
fi

echo "获取 release 信息: $REPO ($VERSION)"
release_json="$(curl -fsSL "$api_url")"
download_url="$(printf '%s\n' "$release_json" | sed -n 's/.*"browser_download_url":[[:space:]]*"\([^"]*\)".*/\1/p' | grep "/$asset$" | head -n 1 || true)"

if [ -z "$download_url" ]; then
  echo "未找到适用于当前平台的 release 资产: $asset" >&2
  echo "请确认 GitHub Release 已生成跨平台可执行文件。" >&2
  exit 1
fi

echo "下载: $asset"
curl -fL "$download_url" -o "$tmp_dir/$asset"
chmod +x "$tmp_dir/$asset"
mv "$tmp_dir/$asset" "$install_dir/$BIN_NAME"

ensure_path_hint "$install_dir"

echo "安装完成: $install_dir/$BIN_NAME"
"$install_dir/$BIN_NAME" --version
