# GitHub Folder Downloader

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/pypi/v/gh-folder-download?color=%2334D058\&label=Version)](https://pypi.org/project/gh-folder-download)
[![Last commit](https://img.shields.io/github/last-commit/leynier/gh-folder-download.svg?style=flat)](https://github.com/leynier/gh-folder-download/commits)
[![Commit activity](https://img.shields.io/github/commit-activity/m/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/commits)
[![Stars](https://img.shields.io/github/stars/leynier/gh-folder-download?style=flat\&logo=github)](https://github.com/leynier/gh-folder-download/stargazers)
[![Forks](https://img.shields.io/github/forks/leynier/gh-folder-download?style=flat\&logo=github)](https://github.com/leynier/gh-folder-download/network/members)
[![Watchers](https://img.shields.io/github/watchers/leynier/gh-folder-download?style=flat\&logo=github)](https://github.com/leynier/gh-folder-download)
[![Contributors](https://img.shields.io/github/contributors/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/graphs/contributors)

A **high-performance CLI** that lets you download individual folders, branches, or entire repositories from GitHub **without cloning** the whole repo. Written in Python with a focus on speed, reliability, and an excellent terminal experience.

---

## Table of Contents

* [Overview](#overview)
* [Key Features](#key-features)
* [Installation](#installation)
* [Quick Start](#quick-start)
* [Configuration](#configuration)
* [Usage Recipes](#usage-recipes)
* [CLI Reference](#cli-reference)
* [Advanced Topics](#advanced-topics)
* [Error Handling](#error-handling)
* [Contributing](#contributing)
* [License](#license)

---

## Overview

`gh-folder-download` helps you grab **just the parts of a repo you need**—perfect for CI pipelines, config backups, documentation syncs, or one-off code reviews—while saving bandwidth and GitHub API quota.

---

## Key Features

* 🚀 **Fast & Parallel** — asyncio-powered downloads with configurable concurrency.
* 📊 **Beautiful Progress Bars** — per-file and overall progress, ETA, speed, and rich colors.
* 💾 **Intelligent Cache** — SHA-based cache prevents re-downloading unchanged files.
* 🔍 **Granular Filtering** — include or exclude by extension, glob pattern, size, or binary type.
* 🏗️ **Smart Rate Limiting** — adaptive GitHub API usage with optional bypass.
* ⚙️ **Flexible Config** — YAML config file, env vars, or CLI flags (with clear precedence).
* ✅ **Integrity Checks** — optional size & hash verification after download.
* 🔄 **Auto Retry** — exponential back-off for network, server, or rate-limit hiccups.

---

## Installation

Run instantly with [uv](https://docs.astral.sh/uv) (no install):

```bash
uvx gh-folder-download --url https://github.com/leynier/gh-folder-download
```

Or install from PyPI:

```bash
# Pick your preferred manager
pip install gh-folder-download
uv add gh-folder-download
poetry add gh-folder-download
conda install gh-folder-download
```

---

## Quick Start

Download a folder from the `main` branch into the current directory:

```bash
gh-folder-download --url https://github.com/user/repo/tree/main/path/to/folder
```

Use a token (private repo) and quiet mode:

```bash
gh-folder-download --url https://github.com/org/private-repo \
                   --token $GITHUB_TOKEN \
                   --quiet
```

---

## Configuration

`gh-folder-download` reads settings in this order (later overrides earlier):

1. Built-in defaults
2. YAML config file (auto or `--config-file`)
3. Environment variables (`GH_FOLDER_DOWNLOAD_*`)
4. CLI flags

### Config File Locations

| Priority | Path                                                   |
| -------- | ------------------------------------------------------ |
| 1        | `./gh-folder-download.yaml`                            |
| 2        | `~/.config/gh-folder-download/gh-folder-download.yaml` |
| 3        | `~/.gh-folder-download.yaml`                           |

Generate a starter file:

```bash
gh-folder-download --create-config
```

### Example Configuration File

```yaml
# GitHub authentication
github_token: "your_github_token_here"

# Download settings
download:
  max_concurrent: 5
  timeout: 30
  chunk_size: 8192
  max_retries: 3
  retry_delay: 1.0
  verify_integrity: true
  parallel_downloads: true

# Cache settings
cache:
  enabled: true
  max_size_gb: 5.0
  max_age_days: 30
  auto_cleanup: true

# Rate limiting
rate_limit:
  enabled: true
  buffer: 100
  aggressive_mode: false

# File filters
filters:
  include_extensions: [".py", ".js", ".md"]
  exclude_extensions: [".log", ".tmp"]
  exclude_binary: false
  exclude_large_files: false
  respect_gitignore: false

# Paths
paths:
  default_output: "."
  create_subdirs: true
  preserve_structure: true

# UI
ui:
  show_progress: true
  verbosity: "INFO"
  use_colors: true
  quiet_mode: false
```

### Environment Variables

```bash
export GH_FOLDER_DOWNLOAD_GITHUB_TOKEN="your_token"
export GH_FOLDER_DOWNLOAD_MAX_CONCURRENT=10
export GH_FOLDER_DOWNLOAD_SHOW_PROGRESS=false
```

---

## Usage Recipes

### Basic Download

```bash
gh-folder-download --url https://github.com/user/repo
```

### Filtering

```bash
gh-folder-download --url https://github.com/user/repo \
                   --include-extensions .py .md \
                   --exclude-patterns "**/test/**" "**/*.pyc"
```

### Performance Profiles

| Profile  | Description          | Recommended Flags                                                                 |
| -------- | -------------------- | --------------------------------------------------------------------------------- |
| Fastest  | For max speed        | `--parallel-downloads --max-concurrent 20 --no-use-cache --disable-rate-limiting` |
| Balanced | Good default         | `--parallel-downloads --max-concurrent 8 --use-cache`                             |
| Reliable | Focus on correctness | `--max-retries 8 --retry-delay 2 --verify-integrity`                              |

---

## CLI Reference

Run `gh-folder-download --help` for the full list. Common options include:

* `--url` (required): GitHub repo or folder URL
* `--output`: Target directory
* `--token`: GitHub personal token
* `--include-extensions`, `--exclude-patterns`: File filters
* `--parallel-downloads`, `--max-concurrent`: Speed tuning
* `--show-progress`, `--quiet`, `--verbose`: Output control

---

## Advanced Topics

* **Progress Bars**: Enable/disable with `--show-progress`
* **Caching**: SHA-based, inspect with `--cache-stats`
* **Rate Limiting**: Adaptive, or override with `--disable-rate-limiting`
* **File Validation**: Use `--verify-integrity`

---

## Error Handling

Handles:

* Network issues (timeouts, DNS, etc.)
* Permission and token errors
* Invalid GitHub URLs or paths
* Disk I/O problems

Use `--verbose` or `--log-file` for deeper diagnostics.

---

## Contributing

PRs welcome! See [`CONTRIBUTING.md`](contributing.md).

---

## License

MIT License. See [`LICENSE`](license).
