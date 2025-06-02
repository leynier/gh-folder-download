# GitHub Folder Downloader

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/pypi/v/gh-folder-download?color=%2334D058&label=Version)](https://pypi.org/project/gh-folder-download)
[![Last commit](https://img.shields.io/github/last-commit/leynier/gh-folder-download.svg?style=flat)](https://github.com/leynier/gh-folder-download/commits)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/commits)
[![Github Stars](https://img.shields.io/github/stars/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/stargazers)
[![Github Forks](https://img.shields.io/github/forks/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/network/members)
[![Github Watchers](https://img.shields.io/github/watchers/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download)
[![GitHub contributors](https://img.shields.io/github/contributors/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/graphs/contributors)

A robust command line application (CLI) to download specific folders from GitHub repositories without downloading the full repository. Built with Python using modern best practices for reliability, performance, and user experience.

## Features

✨ **Smart Logging**: Rich, colorful output with structured logging  
📊 **Progress Tracking**: Real-time download progress with file sizes  
📁 **Flexible Downloads**: Download entire repos, specific branches, or folders  
🔧 **Configurable**: Multiple verbosity levels and log file support  
⚡ **Fast & Reliable**: Built with modern Python and robust error handling  
🔒 **Input Validation**: Comprehensive validation of URLs, paths, and tokens  
🔄 **Auto Retry**: Exponential backoff retry for network failures and rate limits  
✅ **Integrity Verification**: File size and content verification after download  

## Getting Started

The recommended way to use `gh-folder-download` is with [uv](https://docs.astral.sh/uv), which allows you to run it without installation:

```bash
uvx gh-folder-download --url https://github.com/leynier/gh-folder-download
```

But you can also install `gh-folder-download` with:

- `pip install gh-folder-download`
- `uv add gh-folder-download`
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
  --verify-integrity / --no-verify-integrity
                                  Verify file integrity after download
                                  [default: verify-integrity]
  --max-retries INTEGER RANGE [1<=x<=10]
                                  Maximum number of retry attempts for failed
                                  operations [default: 3]
  --retry-delay FLOAT RANGE [0.1<=x<=30.0]
                                  Base delay between retries in seconds
                                  [default: 1.0]
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```

## Enhanced Features

### 🔒 Input Validation

Comprehensive validation ensures robust operation:

- **GitHub URL validation**: Proper format, valid domain, and path structure
- **Path validation**: Output directory permissions and security checks  
- **Token validation**: GitHub token format verification and connectivity testing
- **Parameter validation**: Range checking for retry settings and other options

```bash
# These will show helpful validation errors:
gh-folder-download --url https://invalid-site.com/user/repo  # Invalid domain
gh-folder-download --url https://github.com/user  # Missing repository
gh-folder-download --url https://github.com/user/repo/invalid/path  # Bad path format
```

### 🔄 Automatic Retry with Exponential Backoff

Intelligent retry mechanism handles temporary failures:

- **Network issues**: Connection timeouts, DNS failures, network interruptions
- **GitHub API limits**: Rate limiting with intelligent backoff delays
- **Server errors**: 5xx status codes with progressive retry delays
- **Configurable**: Customize retry attempts and delay timing

```bash
# Custom retry configuration
gh-folder-download --url URL --max-retries 5 --retry-delay 2.0

# For unstable networks
gh-folder-download --url URL --max-retries 8 --retry-delay 3.0
```

**Retry Strategy:**

- API calls: Conservative (3 attempts, 1-30s delays)
- Downloads: Aggressive (5 attempts, 2-120s delays)
- Exponential backoff with jitter to avoid thundering herd
- Special handling for GitHub rate limits (minimum 60s delay)

### ✅ File Integrity Verification

Comprehensive integrity checking ensures download quality:

- **Size verification**: Compares downloaded file size with expected size
- **Content analysis**: Detects corruption, empty files, and accessibility issues
- **Checksum support**: MD5, SHA1, and SHA256 hash calculations
- **Binary detection**: Identifies file types and potential issues

```bash
# Enable integrity verification (default)
gh-folder-download --url URL --verify-integrity

# Disable for faster downloads
gh-folder-download --url URL --no-verify-integrity

# View detailed verification in verbose mode
gh-folder-download --url URL --verbose
```

**Verification Process:**

1. File size validation against GitHub API metadata
2. File accessibility and readability checks
3. Content type detection (text vs binary)
4. Empty file detection
5. Basic corruption detection

## Logging Options

### Verbosity Levels

- **Default**: Shows progress, downloads, and summary with rich formatting
- **Verbose (`-v/--verbose`)**: Includes debug information like API calls, validation details, retry attempts
- **Quiet (`-q/--quiet`)**: Only shows errors in console
- **Log File (`--log-file`)**: Saves all events to a file regardless of console verbosity

### Examples

```bash
# Standard output with rich formatting
gh-folder-download --url https://github.com/user/repo/tree/main/src

# Detailed debug information with retry logging
gh-folder-download --url https://github.com/user/repo --verbose

# Silent mode for automation
gh-folder-download --url https://github.com/user/repo --quiet

# Complete audit trail
gh-folder-download --url https://github.com/user/repo --quiet --log-file download.log

# Development debugging
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
- Retry attempt logging
- Integrity verification status

### Summary Statistics

- Total files downloaded
- Total size downloaded
- Download duration
- Average download speed
- Integrity verification results

## Authentication

For private repositories or to avoid rate limits, provide a GitHub token:

```bash
# Via command line
gh-folder-download --url https://github.com/private/repo --token your_token_here

# Via environment variable (recommended)
export GITHUB_TOKEN=your_token_here
gh-folder-download --url https://github.com/private/repo
```

**Token Types Supported:**

- Classic Personal Access Tokens (`ghp_xxxxxxxxxxxx`)
- Fine-grained Personal Access Tokens (`github_pat_xxxxxxxxx`)
- Legacy tokens (40-character alphanumeric)

## Error Handling

The tool provides detailed error messages for common issues:

### Network & Connectivity

- Connection timeouts with retry information
- DNS resolution failures
- Network interruption recovery
- GitHub API server errors

### Authentication & Permissions

- Invalid token format validation
- Authentication failures with clear messages
- Permission denied errors
- Rate limiting with wait time estimates

### Input Validation

- Malformed GitHub URLs with format examples
- Invalid branch/tag names
- Path security validation
- Output directory permission checks

### File Operations

- Download corruption detection
- Disk space and permission issues
- File integrity verification failures
- Partial download recovery

All errors are logged with full context when using `--verbose` or `--log-file`, making debugging straightforward.

## Configuration Examples

### High Reliability Setup

```bash
# Maximum reliability for critical downloads
gh-folder-download \
  --url https://github.com/important/repo \
  --max-retries 8 \
  --retry-delay 2.0 \
  --verify-integrity \
  --verbose \
  --log-file critical-download.log
```

### Fast Download Setup

```bash
# Optimized for speed
gh-folder-download \
  --url https://github.com/user/repo \
  --max-retries 2 \
  --retry-delay 0.5 \
  --no-verify-integrity \
  --quiet
```

### Automation/CI Setup

```bash
# Perfect for scripts and CI/CD
gh-folder-download \
  --url https://github.com/user/repo/tree/main/configs \
  --output ./configs \
  --force \
  --quiet \
  --log-file deployment.log \
  --max-retries 5
```
