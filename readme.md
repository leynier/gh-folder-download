# GitHub Folder Downloader

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/pypi/v/gh-folder-download?color=%2334D058&label=Version)](https://pypi.org/project/gh-folder-download)
[![Last commit](https://img.shields.io/github/last-commit/leynier/gh-folder-download.svg?style=flat)](https://github.com/leynier/gh-folder-download/commits)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/commits)
[![Github Stars](https://img.shields.io/github/stars/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/stargazers)
[![Github Forks](https://img.shields.io/github/forks/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/network/members)
[![Github Watchers](https://img.shields.io/github/watchers/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download)
[![GitHub contributors](https://img.shields.io/github/contributors/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/graphs/contributors)

A command line application (CLI) to download only a specific folder without downloading the full repository implemented with Python using Typer and GitHub API.

## Features

✨ **Smart Logging**: Rich, colorful output with structured logging  
📊 **Progress Tracking**: Real-time download progress with file sizes  
📁 **Flexible Downloads**: Download entire repos, specific branches, or folders  
🔧 **Configurable**: Multiple verbosity levels and log file support  
⚡ **Fast & Reliable**: Built with modern Python and robust error handling  

## Getting Started

Install `gh-folder-download` with:

- `pip install gh-folder-download`
- `poetry add gh-folder-download`
- `conda install gh-folder-download`
- Any other way that allows you to install the package from PyPI.

## Commands

```bash
Usage: gh-folder-download [OPTIONS]

Options:
  --url TEXT                      Repository URL  [required]
  --output DIRECTORY              Output folder  [default: .]
  --token TEXT                    GitHub token
  --force / --no-force            Remove existing output folder if it exists
                                  [default: no-force]
  --verbose, -v                   Enable verbose logging (debug information)
  --quiet, -q                     Suppress output except errors
  --log-file PATH                 Log to file (captures all events)
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```

## Logging Options

### Verbosity Levels

- **Default**: Shows progress, downloads, and summary with rich formatting
- **Verbose (`-v/--verbose`)**: Includes debug information like API calls, parsing details
- **Quiet (`-q/--quiet`)**: Only shows errors in console
- **Log File (`--log-file`)**: Saves all events to a file regardless of console verbosity

### Examples

```bash
# Standard output with rich formatting
gh-folder-download --url https://github.com/user/repo/tree/main/src

# Detailed debug information
gh-folder-download --url https://github.com/user/repo --verbose

# Silent mode (only errors shown)
gh-folder-download --url https://github.com/user/repo --quiet

# Log everything to file while staying quiet
gh-folder-download --url https://github.com/user/repo --quiet --log-file download.log

# Verbose output + file logging
gh-folder-download --url https://github.com/user/repo --verbose --log-file debug.log
```

## GitHub Repository URL format

- `https://github.com/{user_or_organization}/{repository_name}`
  > Download the full repository from the default branch.
- `https://github.com/{user_or_organization}/{repository_name}/tree/{branch}`
  > Download the full repository from the specified branch.
- `https://github.com/{user_or_organization}/{repository_name}/tree/{branch}/{folder_path}`
  > Download the specified folder from the specified branch.

## Output Features

### Repository Information

Displays a formatted table with:

- Organization/User name
- Repository name  
- Branch being downloaded
- Specific path (if any)

### Download Progress

- Real-time file download notifications
- File sizes in human-readable format
- Success/error indicators with colors

### Summary Statistics

- Total files downloaded
- Total size downloaded
- Download duration
- Average download speed

## Authentication

For private repositories or to avoid rate limits, provide a GitHub token:

```bash
# Via command line
gh-folder-download --url https://github.com/private/repo --token your_token_here

# Via environment variable
export GITHUB_TOKEN=your_token_here
gh-folder-download --url https://github.com/private/repo
```

## Error Handling

The tool provides detailed error messages for common issues:

- Invalid GitHub URLs
- Non-existent repositories or branches
- Permission denied errors
- Network connectivity issues
- API rate limit exceeded

All errors are logged with full context when using `--verbose` or `--log-file`.
