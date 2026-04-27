# Release Process

This project ships a CLI, so each user-visible release must be versioned,
tagged, and installable from stable GitHub Release binaries.

## Why an install can look stale

`pipx install git+https://github.com/weijunjiang123/skill-repo.git` installs
from the repository default branch at install time. It does not automatically
track open pull requests or reinstall an already installed app.

Common causes of seeing an old CLI:

- the change is on a feature branch or PR, not merged into the default branch;
- the local `pipx` app already exists and needs `pipx upgrade` or reinstall;
- the package version was not bumped, making it hard to verify what is running;
- the shell is finding another `skill-repo` earlier on `PATH`.

Check the active binary with:

```bash
which skill-repo
skill-repo --version
pipx list | grep skill-repo
```

## Versioning

Use semantic versions:

- patch: bug fixes only, for example `0.2.1`;
- minor: new platform support or backward-compatible features, for example `0.3.0`;
- major: breaking CLI/config behavior, for example `1.0.0`.

Keep these files in sync for every release:

- `pyproject.toml`
- `src/skill_repo/__init__.py`
- `uv.lock`
- install snippets in `README.md`
- install snippets in `src/skill_repo/_templates/default_skill_repo_cli.md`
- release binary names in `.github/workflows/release-binaries.yml` and install scripts, if a platform changes

## Release checklist

1. Update the version in `pyproject.toml` and `src/skill_repo/__init__.py`.
2. Update README/template install examples to the new tag, for example `v0.2.0`.
3. Run targeted and full tests:

   ```bash
   uv run pytest tests/test_platforms.py tests/test_skill_manager.py
   uv run pytest
   ```

4. Commit the release prep:

   ```bash
   git add pyproject.toml src/skill_repo/__init__.py uv.lock README.md src/skill_repo/_templates/default_skill_repo_cli.md docs/RELEASE.md
   git commit -m "Prepare v0.2.0 release"
   ```

5. Merge the PR into the default branch.
6. Tag the merged commit and push the tag:

   ```bash
   git checkout master
   git pull --ff-only
   git tag -a v0.2.0 -m "v0.2.0"
   git push origin v0.2.0
   ```

7. Create and publish a GitHub Release for the tag. The `Release binaries`
   workflow runs on `release.published`, builds Nuitka executables, verifies
   `skill-repo --version`, and uploads these assets:

   - `skill-repo-linux-x64`
   - `skill-repo-linux-arm64`
   - `skill-repo-macos-x64`
   - `skill-repo-macos-arm64`
   - `skill-repo-windows-x64.exe`

8. If a release upload needs to be retried, run the `Release binaries` workflow
   manually with the existing tag.

9. Ask users to install or upgrade with the zero-config installer:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/weijunjiang123/skill-repo/v0.2.0/scripts/install-binary.sh | sh
   ```

   ```powershell
   irm https://raw.githubusercontent.com/weijunjiang123/skill-repo/v0.2.0/scripts/install-binary.ps1 | iex
   ```

## Source install fallback

If binary assets are not available for a platform, developers can still install
from a tagged Git ref:

```bash
pipx install "git+https://github.com/weijunjiang123/skill-repo.git@v0.2.0"
skill-repo --version
```
