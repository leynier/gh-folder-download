# GitHub Folder Downloader

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/gh-folder-download)](https://pypi.org/project/gh-folder-download)

`gh-folder-download` downloads a repository or one of its folders without cloning its Git history. It provides
parallel transfers, transactional replacement, Git blob integrity checks, content-addressed caching, filters, retries,
rate-limit awareness, and YAML/environment configuration.

## Installation

Python 3.13 or newer is required.

```bash
uvx gh-folder-download --url https://github.com/leynier/gh-folder-download
# or
pip install gh-folder-download
```

## Destination behavior

`--output` is always a **parent directory**:

```text
Repository URL                           Destination
https://github.com/user/project          OUTPUT/project
https://github.com/user/project/tree/main/docs/guides
                                         OUTPUT/docs/guides
```

An existing calculated destination is rejected unless `--force` is supplied. Forced downloads are prepared and
verified in a sibling staging directory first; the existing destination is replaced only after every selected file
succeeds. `--force` never removes the directory passed directly to `--output`.

## Usage

```bash
# Download a complete repository into ./project
gh-folder-download --url https://github.com/user/project

# Download one folder
gh-folder-download \
  --url https://github.com/user/project/tree/main/docs \
  --output ./downloads

# Use an unambiguous branch name containing slashes
gh-folder-download \
  --url https://github.com/user/project \
  --ref feature/new-docs \
  --path docs

# Replace a previous destination and reuse verified cached blobs
gh-folder-download --url https://github.com/user/project --force --use-cache

# Download only Python files that are not ignored by the repository
gh-folder-download \
  --url https://github.com/user/project \
  --include-extensions .py \
  --respect-gitignore
```

Run `gh-folder-download --help` for every option. Useful standalone cache commands are:

```bash
gh-folder-download --cache-stats
gh-folder-download --clear-cache
```

## Configuration

Configuration precedence is:

1. Built-in defaults
2. The first discovered YAML file, or `--config-file`
3. `GH_FOLDER_DOWNLOAD_*` environment variables
4. Explicit CLI options

Files are discovered in this order:

1. `./gh-folder-download.yaml`
2. `~/.config/gh-folder-download/gh-folder-download.yaml`
3. `~/.gh-folder-download.yaml`

Generate a documented example with:

```bash
gh-folder-download --create-config
```

Example:

```yaml
download:
  max_concurrent: 5
  timeout: 30
  chunk_size: 8192
  max_retries: 3
  retry_delay: 1.0
  verify_integrity: true
  parallel_downloads: true

cache:
  enabled: true
  max_size_gb: 5.0
  max_age_days: 30
  auto_cleanup: true

rate_limit:
  enabled: true
  buffer: 100

filters:
  include_extensions: [".py", ".md"]
  exclude_patterns: ["**/generated/**"]
  exclude_binary: false
  exclude_large_files: false
  respect_gitignore: true

paths:
  default_output: "."

ui:
  show_progress: true
  verbosity: "INFO"
  use_colors: true
  quiet_mode: false
```

Supported environment variables include:

```bash
export GH_FOLDER_DOWNLOAD_GITHUB_TOKEN="github_pat_..."
export GH_FOLDER_DOWNLOAD_MAX_CONCURRENT=10
export GH_FOLDER_DOWNLOAD_SHOW_PROGRESS=false
```

`GITHUB_TOKEN` is also accepted as a fallback when no CLI/config namespaced token is set.

## Reliability and exit codes

- `0`: traversal and installation completed, including a valid filter that selected zero files.
- `1`: remote, download, integrity, cache, or destination failure.
- `2`: invalid CLI input, URL, path, or configuration.

Downloads use temporary `.part` files, retry transient HTTP failures with exponential backoff, verify the Git blob SHA
when integrity checks are enabled, and install the staged directory only after complete success. Expected failures are
shown without a traceback; use `--verbose` for diagnostic tracebacks.

## Development

```bash
make check        # lint, format check, types, offline tests, and package build
make integration  # network tests against GitHub
```

The offline suite enforces 100% line coverage for the `gh_folder_download` package. Network tests use pytest temporary
directories and are excluded from the default test run. See
[`contributing.md`](contributing.md) for contribution guidelines.

## License

MIT. See [`license`](license).
