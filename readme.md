# GitHub Folder Downloader

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/pypi/v/gh-folder-download?color=%2334D058&label=Version)](https://pypi.org/project/gh-folder-download)
[![Last commit](https://img.shields.io/github/last-commit/leynier/gh-folder-download.svg?style=flat)](https://github.com/leynier/gh-folder-download/commits)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/commits)
[![Github Stars](https://img.shields.io/github/stars/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/stargazers)
[![Github Forks](https://img.shields.io/github/forks/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download/network/members)
[![Github Watchers](https://img.shields.io/github/watchers/leynier/gh-folder-download?style=flat&logo=github)](https://github.com/leynier/gh-folder-download)
[![GitHub contributors](https://img.shields.io/github/contributors/leynier/gh-folder-download)](https://github.com/leynier/gh-folder-download/graphs/contributors)

A robust, high-performance command line application (CLI) to download specific folders from GitHub repositories without downloading the full repository. Built with Python using modern best practices for reliability, performance, and user experience.

## Features

✨ **Smart Logging**: Rich, colorful output with structured logging  
📊 **Advanced Progress Bars**: Real-time progress tracking with individual file progress, ETA, and speed  
📁 **Flexible Downloads**: Download entire repos, specific branches, or folders  
🔧 **Configurable**: Multiple verbosity levels and log file support  
⚡ **Fast & Reliable**: Built with modern Python and robust error handling  
🔒 **Input Validation**: Comprehensive validation of URLs, paths, and tokens  
🔄 **Auto Retry**: Exponential backoff retry for network failures and rate limits  
✅ **Integrity Verification**: File size and content verification after download  
🚀 **Parallel Downloads**: Concurrent downloads for maximum speed  
💾 **Intelligent Caching**: Avoid re-downloading unchanged files  
🏗️ **Rate Limiting**: Smart GitHub API usage with automatic throttling  

## User Experience Features

### 📊 Advanced Progress Bars

Rich, real-time progress tracking with detailed statistics:

- **Individual file progress**: Each file shows its own progress bar with filename, percentage, size, and speed
- **Overall progress**: Master progress bar showing total completion across all files
- **Real-time statistics**: Live updates of download speed, estimated time remaining (ETA), and completion percentage
- **Visual feedback**: Colorful spinners, bars, and status indicators
- **Smart file naming**: Truncated filenames for clean display

```bash
╭──────────────────────────────────────── 📊 Download Information ─────────────────────────────────────────╮
│      Download Session                                                                                    │
│ ┏━━━━━━━━━━━━━┳━━━━━━━━━━┓                                                                               │
│ ┃ Metric      ┃    Value ┃                                                                               │
│ ┡━━━━━━━━━━━━━╇━━━━━━━━━━┩                                                                               │
│ │ Total Files │       25 │                                                                               │
│ │ Total Size  │  15.2 MB │                                                                               │
│ │ Started     │ 14:23:15 │                                                                               │
│ └─────────────┴──────────┘                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────╯

⠸ Overall Progress (25 files) ━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━━ 65.4% • 9.9/15.2 MB • 2.1 MB/s • 0:00:03
⠋ main.py                    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 89.2% • 45.6/51.2 kB • 1.8 MB/s • 0:00:01
⠙ utils.py                   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100.0% • 32.1/32.1 kB • 2.3 MB/s • 0:00:00
⠹ config.yaml               ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100.0% • 2.4/2.4 kB • 1.2 MB/s • 0:00:00
```

### 🎯 Performance Metrics

Comprehensive performance tracking and statistics:

- **Download speed**: Real-time speed in B/s, KB/s, MB/s or GB/s
- **ETA calculation**: Smart time estimation based on current speed and remaining data
- **Cache efficiency**: Track and display cache hit rates
- **Success rates**: Monitor and report download success/failure rates
- **Completion tracking**: Files completed vs total with percentage

### 📈 Final Summary

Detailed completion report with performance metrics:

```bash
╭────────────────────────────────────────── ✅ Download Complete ──────────────────────────────────────────╮
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓                                                                  │
│ ┃ Metric                  ┃     Value ┃                                                                  │
│ ┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩                                                                  │
│ │ Total Files             │        25 │                                                                  │
│ │ Successfully Downloaded │        24 │                                                                  │
│ │ From Cache              │         8 │                                                                  │
│ │ Failed                  │         1 │                                                                  │
│ │                         │           │                                                                  │
│ │ Total Downloaded        │   15.2 MB │                                                                  │
│ │ Total Time              │      7.3s │                                                                  │
│ │ Average Speed           │  2.1 MB/s │                                                                  │
│ │ Success Rate            │     96.0% │                                                                  │
│ │ Cache Hit Rate          │     33.3% │                                                                  │
│ └─────────────────────────┴───────────┘                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### 🎮 Progress Control Options

Control the progress display experience:

```bash
# Full progress experience (default)
gh-folder-download --url URL --show-progress

# Disable progress bars for clean output
gh-folder-download --url URL --no-show-progress

# Quiet mode - minimal output
gh-folder-download --url URL --quiet

# Verbose mode with detailed progress
gh-folder-download --url URL --verbose
```

## Configuration & File Filtering

### 📋 Configuration System

gh-folder-download supports flexible configuration through files, environment variables, and command-line options.

#### Configuration File

Create a configuration file to set default values and avoid repetitive command-line options:

```bash
# Generate a sample configuration file
gh-folder-download --create-config

# Use a specific config file
gh-folder-download --config-file my-config.yaml --url REPO_URL
```

**Configuration File Locations** (in order of priority):

1. Current directory: `./gh-folder-download.yaml`
2. User config directory: `~/.config/gh-folder-download/gh-folder-download.yaml` (Linux/macOS)
3. User home directory: `~/.gh-folder-download.yaml`

**Sample Configuration:**

```yaml
# GitHub authentication
github_token: "your_github_token_here"

# Download settings
download:
  max_concurrent: 8
  timeout: 60
  max_retries: 5
  verify_integrity: true

# Cache settings
cache:
  enabled: true
  max_size_gb: 10.0
  max_age_days: 60

# File filtering
filters:
  include_extensions: [".py", ".js", ".md"]
  exclude_patterns: ["**/test/**", "**/*.pyc"]
  exclude_binary: true
  respect_gitignore: true

# UI preferences
ui:
  show_progress: true
  verbosity: "INFO"
  use_colors: true
```

#### Environment Variables

Override configuration with environment variables:

```bash
export GH_FOLDER_DOWNLOAD_GITHUB_TOKEN="your_token"
export GH_FOLDER_DOWNLOAD_MAX_CONCURRENT=10
export GH_FOLDER_DOWNLOAD_CACHE_ENABLED=true
export GH_FOLDER_DOWNLOAD_SHOW_PROGRESS=false
```

### 🔍 Advanced File Filtering

Filter files by extension, size, patterns, and content type for precise downloads.

#### Extension Filters

```bash
# Download only Python and Markdown files
gh-folder-download --url REPO_URL --include-extensions .py .md

# Exclude log and temporary files
gh-folder-download --url REPO_URL --exclude-extensions .log .tmp .cache

# Combine with other filters
gh-folder-download --url REPO_URL --include-extensions .js .ts --exclude-patterns "**/node_modules/**"
```

#### Size Filters

```bash
# Files between 1KB and 10MB
gh-folder-download --url REPO_URL --min-size 1KB --max-size 10MB

# Only small files (under 1MB)
gh-folder-download --url REPO_URL --max-size 1MB

# Exclude tiny files
gh-folder-download --url REPO_URL --min-size 100B
```

**Supported Size Units:** B, KB, MB, GB, TB

#### Pattern Filters

Use glob patterns for sophisticated filtering:

```bash
# Include specific directories
gh-folder-download --url REPO_URL --include-patterns "src/**" "docs/**"

# Exclude test directories and compiled files
gh-folder-download --url REPO_URL --exclude-patterns "**/test/**" "**/*.pyc" "**/*.o"

# Complex pattern matching
gh-folder-download --url REPO_URL \
  --include-patterns "src/**/*.py" "config/*.yaml" \
  --exclude-patterns "**/test_*" "**/__pycache__/**"
```

#### Content-Based Filters

```bash
# Exclude binary files (images, executables, etc.)
gh-folder-download --url REPO_URL --exclude-binary

# Exclude large files (>10MB)
gh-folder-download --url REPO_URL --exclude-large-files

# Respect common .gitignore patterns
gh-folder-download --url REPO_URL --respect-gitignore
```

#### Filter Presets

Use predefined filter combinations for common scenarios:

```bash
# Download only source code files
gh-folder-download --url REPO_URL --filter-preset code-only

# Download only documentation
gh-folder-download --url REPO_URL --filter-preset docs-only

# Download only configuration files
gh-folder-download --url REPO_URL --filter-preset config-only

# Exclude test files
gh-folder-download --url REPO_URL --filter-preset no-tests

# Download only small files
gh-folder-download --url REPO_URL --filter-preset small-files

# Minimal download (fastest)
gh-folder-download --url REPO_URL --filter-preset minimal
```

**Available Presets:**

| Preset | Description | Includes | Excludes |
|--------|-------------|----------|----------|
| `code-only` | Source code files | .py, .js, .ts, .java, .c, .cpp, .go, .rs, .php, .rb, etc. | Binary files, large files, gitignored files |
| `docs-only` | Documentation files | .md, .rst, .txt, .html, docs/, README*, LICENSE* | Everything else |
| `config-only` | Configuration files | .yaml, .json, .toml, .ini, .cfg, config/, .env | Everything else |
| `no-tests` | Exclude test files | All files | test/, tests/, *_test.*, *Test.* |
| `small-files` | Small files only | Files < 1MB | Binary files, large files |
| `minimal` | Essential files | .md, .txt, .py, .js, .html, .css | Binary, large files, gitignored |

#### Complex Filtering Examples

**Code Review Preparation:**

```bash
gh-folder-download --url REPO_URL \
  --include-extensions .py .js .ts .html .css .md \
  --exclude-patterns "**/test/**" "**/*.min.js" \
  --exclude-binary \
  --max-size 500KB \
  --respect-gitignore
```

**Documentation Extraction:**

```bash
gh-folder-download --url REPO_URL \
  --filter-preset docs-only \
  --include-patterns "README*" "CHANGELOG*" "LICENSE*" \
  --max-size 10MB
```

**Configuration Backup:**

```bash
gh-folder-download --url REPO_URL \
  --filter-preset config-only \
  --include-patterns ".github/**" "docker-compose.*" \
  --max-size 1MB
```

**Quick Source Code Scan:**

```bash
gh-folder-download --url REPO_URL \
  --filter-preset minimal \
  --exclude-patterns "**/vendor/**" "**/node_modules/**" \
  --max-size 100KB
```

#### Combining Filters

Filters work together logically:

1. **Include Extensions** → File must match at least one extension
2. **Exclude Extensions** → File must not match any extension
3. **Include Patterns** → File must match at least one pattern
4. **Exclude Patterns** → File must not match any pattern
5. **Size Filters** → File size must be within range
6. **Binary Filter** → File must not be binary (if enabled)
7. **Large File Filter** → File must not be >10MB (if enabled)
8. **Gitignore Filter** → File must not match gitignore patterns (if enabled)

All filters must pass for a file to be included.

### 🎯 Practical Use Cases

#### Development Workflow

```bash
# Daily code sync
gh-folder-download --url REPO_URL \
  --filter-preset code-only \
  --use-cache \
  --show-progress

# Quick documentation update
gh-folder-download --url REPO_URL/tree/main/docs \
  --filter-preset docs-only \
  --output ./docs
```

#### DevOps & Configuration

```bash
# Infrastructure config backup
gh-folder-download --url REPO_URL \
  --include-patterns "*.yml" "*.yaml" "Dockerfile*" "*.env" \
  --output ./configs

# CI/CD pipeline files
gh-folder-download --url REPO_URL \
  --include-patterns ".github/**" ".gitlab-ci.yml" "Jenkinsfile" \
  --output ./pipelines
```

#### Research & Analysis

```bash
# Code analysis (no tests, no binaries)
gh-folder-download --url REPO_URL \
  --filter-preset code-only \
  --exclude-patterns "**/test/**" "**/tests/**" \
  --max-size 1MB

# License and legal review
gh-folder-download --url REPO_URL \
  --include-patterns "LICENSE*" "COPYING*" "NOTICE*" "LEGAL*" \
  --include-extensions .txt .md
```

## Performance & Scalability Features

### 🚀 Parallel Downloads

Download multiple files simultaneously using asyncio for maximum throughput:

- **Concurrent downloads**: Configure up to 20 simultaneous downloads
- **Intelligent throttling**: Automatic semaphore-based concurrency control
- **Stream processing**: Memory-efficient chunk-based downloading
- **Error isolation**: Individual file failures don't affect other downloads

```bash
# Enable parallel downloads with custom concurrency
gh-folder-download --url URL --parallel-downloads --max-concurrent 10

# Disable parallel downloads for compatibility
gh-folder-download --url URL --no-parallel-downloads
```

### 💾 Intelligent Caching System

Avoid unnecessary re-downloads with SHA-based caching:

- **File metadata tracking**: SHA, size, and modification time comparison
- **Automatic invalidation**: Detects file changes on GitHub
- **Persistent storage**: Cache survives between sessions
- **Integrity verification**: Ensures cached files are still valid

```bash
# Use caching (default)
gh-folder-download --url URL --use-cache

# Disable caching
gh-folder-download --url URL --no-use-cache

# Clear cache before download
gh-folder-download --url URL --clear-cache

# Show cache statistics
gh-folder-download --url URL --cache-stats
```

**Cache Benefits:**

- Up to 100% speedup for unchanged files
- Reduced GitHub API usage
- Bandwidth conservation
- Faster incremental updates

### 🏗️ Smart Rate Limiting

Intelligent GitHub API rate limit management:

- **Real-time monitoring**: Tracks API usage and remaining requests
- **Adaptive delays**: Dynamic timing based on current usage
- **Buffer management**: Reserves requests to prevent hitting limits
- **Automatic recovery**: Waits for rate limit reset when needed
- **Bypass option**: Completely disable rate limiting for maximum speed

```bash
# Configure rate limit buffer (default: 100 requests)
gh-folder-download --url URL --rate-limit-buffer 200

# Conservative setting for shared tokens
gh-folder-download --url URL --rate-limit-buffer 500

# Disable rate limiting completely (may exhaust API limits)
gh-folder-download --url URL --disable-rate-limiting
```

**Rate Limiting Features:**

- Prevents 403 rate limit errors
- Distributes requests evenly over time
- Handles both Core and Search API limits
- Provides detailed usage statistics
- **NEW**: Option to bypass for maximum performance

**⚠️ Important Note about `--disable-rate-limiting`:**

This option provides maximum download speed by completely bypassing GitHub's rate limiting protection. Use with caution:

- **May exhaust your API limits**: Can lead to 403 errors and temporary blocks
- **Best for**: High-limit tokens, one-time downloads, or testing
- **Not recommended for**: Shared tokens, frequent use, or automated scripts
- **Alternative**: Increase `--rate-limit-buffer` for more aggressive but safer behavior

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
  --parallel-downloads / --no-parallel-downloads
                                  Enable parallel downloads for better
                                  performance [default: parallel-downloads]
  --max-concurrent INTEGER RANGE [1<=x<=20]
                                  Maximum number of concurrent downloads
                                  [default: 5]
  --use-cache / --no-use-cache    Enable intelligent caching to avoid
                                  re-downloading unchanged files
                                  [default: use-cache]
  --clear-cache / --no-clear-cache
                                  Clear download cache before starting
                                  [default: no-clear-cache]
  --cache-stats / --no-cache-stats
                                  Show cache statistics
                                  [default: no-cache-stats]
  --rate-limit-buffer INTEGER RANGE [10<=x<=1000]
                                  Number of GitHub API requests to keep as
                                  buffer [default: 100]
  --disable-rate-limiting / --no-disable-rate-limiting
                                  Disable rate limiting completely for maximum
                                  speed (may exhaust API limits)
                                  [default: no-disable-rate-limiting]
  --show-progress / --no-show-progress
                                  Show advanced progress bars and real-time
                                  statistics [default: show-progress]
  
  # Configuration Options
  --config-file PATH              Path to configuration file
  --create-config                 Create a sample configuration file and exit
  
  # File Filtering Options
  --include-extensions TEXT       Include only files with these extensions 
                                  (e.g., --include-extensions .py .js)
  --exclude-extensions TEXT       Exclude files with these extensions 
                                  (e.g., --exclude-extensions .log .tmp)
  --include-patterns TEXT         Include files matching these glob patterns 
                                  (e.g., --include-patterns 'src/**' 'docs/**')
  --exclude-patterns TEXT         Exclude files matching these glob patterns 
                                  (e.g., --exclude-patterns '**/test/**' '**/*.pyc')
  --min-size TEXT                 Minimum file size (e.g., --min-size 1KB, 1MB)
  --max-size TEXT                 Maximum file size (e.g., --max-size 10MB, 100KB)
  --exclude-binary / --no-exclude-binary
                                  Exclude binary files [default: no-exclude-binary]
  --exclude-large-files / --no-exclude-large-files
                                  Exclude files larger than 10MB
                                  [default: no-exclude-large-files]
  --respect-gitignore / --no-respect-gitignore
                                  Respect common .gitignore patterns
                                  [default: no-respect-gitignore]
  --filter-preset TEXT            Use a predefined filter preset (code-only, 
                                  docs-only, config-only, no-tests, small-files, 
                                  minimal)
                                  
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

## Performance Optimization Examples

### 🚀 Maximum Speed Configuration

Optimized for fastest possible downloads:

```bash
gh-folder-download \
  --url https://github.com/user/repo \
  --parallel-downloads \
  --max-concurrent 15 \
  --use-cache \
  --no-verify-integrity \
  --max-retries 2 \
  --retry-delay 0.5 \
  --disable-rate-limiting
```

### 🔄 Balanced Performance Configuration

Good balance of speed and reliability:

```bash
gh-folder-download \
  --url https://github.com/user/repo \
  --parallel-downloads \
  --max-concurrent 8 \
  --use-cache \
  --verify-integrity \
  --max-retries 3 \
  --rate-limit-buffer 150
```

### 🛡️ Maximum Reliability Configuration

Optimized for reliability over speed:

```bash
gh-folder-download \
  --url https://github.com/user/repo \
  --parallel-downloads \
  --max-concurrent 3 \
  --use-cache \
  --verify-integrity \
  --max-retries 8 \
  --retry-delay 2.0 \
  --rate-limit-buffer 300 \
  --verbose \
  --log-file download.log
```

### 📊 Monitoring and Analytics

Track download performance and cache efficiency:

```bash
# Show detailed statistics
gh-folder-download \
  --url https://github.com/user/repo \
  --verbose \
  --cache-stats \
  --log-file analytics.log

# Monitor rate limiting
gh-folder-download \
  --url https://github.com/user/repo \
  --verbose \
  --rate-limit-buffer 50  # Lower buffer shows more rate limit info
```

### ⚡ Extreme Speed Configuration (Use with caution)

For maximum speed when API limits are not a concern:

```bash
gh-folder-download \
  --url https://github.com/user/repo \
  --parallel-downloads \
  --max-concurrent 20 \
  --no-use-cache \
  --no-verify-integrity \
  --max-retries 1 \
  --retry-delay 0.1 \
  --disable-rate-limiting
```

## Logging Options

### Verbosity Levels

- **Default**: Shows progress, downloads, and summary with rich formatting
- **Verbose (`-v/--verbose`)**: Includes debug information like API calls, validation details, retry attempts, cache hits, and rate limiting
- **Quiet (`-q/--quiet`)**: Only shows errors in console
- **Log File (`--log-file`)**: Saves all events to a file regardless of console verbosity

### Examples

```bash
# Standard output with rich formatting
gh-folder-download --url https://github.com/user/repo/tree/main/src

# Detailed debug information with performance metrics
gh-folder-download --url https://github.com/user/repo --verbose

# Silent mode for automation
gh-folder-download --url https://github.com/user/repo --quiet

# Complete audit trail with performance data
gh-folder-download --url https://github.com/user/repo --quiet --log-file download.log

# Development debugging with cache and rate limit info
gh-folder-download --url https://github.com/user/repo --verbose --cache-stats --log-file debug.log
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

- Real-time file download notifications with parallel status
- File sizes in human-readable format
- Success/error indicators with colors
- Retry attempt logging
- Integrity verification status
- Cache hit notifications
- Rate limiting information

### Performance Statistics

- Total files downloaded vs cached
- Total size downloaded
- Download duration and average speed
- Cache hit rate percentage
- Success rate percentage
- Rate limit usage statistics

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
- Cache consistency issues

### Performance Issues

- Rate limit exhaustion with recovery time
- Parallel download failures
- Cache corruption detection
- Memory usage warnings

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
  --parallel-downloads \
  --max-concurrent 3 \
  --use-cache \
  --rate-limit-buffer 300 \
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
  --parallel-downloads \
  --max-concurrent 15 \
  --use-cache \
  --rate-limit-buffer 50 \
  --quiet
```

### Ultra-Fast Download Setup

```bash
# Maximum speed (may exhaust API limits)
gh-folder-download \
  --url https://github.com/user/repo \
  --max-retries 1 \
  --retry-delay 0.1 \
  --no-verify-integrity \
  --parallel-downloads \
  --max-concurrent 20 \
  --no-use-cache \
  --disable-rate-limiting \
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
  --max-retries 5 \
  --parallel-downloads \
  --max-concurrent 8 \
  --use-cache \
  --verify-integrity
```

### Development/Testing Setup

```bash
# Great for development with full monitoring
gh-folder-download \
  --url https://github.com/user/repo \
  --verbose \
  --cache-stats \
  --verify-integrity \
  --parallel-downloads \
  --max-concurrent 5 \
  --log-file dev-download.log
```

## Cache Management

The intelligent caching system stores file metadata in `~/.gh-folder-download/cache/`:

```bash
# View cache statistics
gh-folder-download --url URL --cache-stats

# Clear cache before download
gh-folder-download --url URL --clear-cache

# Disable caching entirely
gh-folder-download --url URL --no-use-cache
```

**Cache Features:**

- Persistent between sessions
- Automatic cleanup of old entries
- Size and age tracking
- Integrity verification
- Cross-platform compatibility

## Performance Benchmarks

Typical performance improvements with new features:

- **Parallel Downloads**: 3-10x faster depending on file count and sizes
- **Intelligent Caching**: Up to 100% speedup for unchanged files
- **Rate Limiting**: Prevents delays from hitting API limits
- **Combined**: Can achieve 5-50x improvement in real-world scenarios

Performance varies based on:

- Network bandwidth and latency
- Repository structure (many small vs few large files)
- GitHub API rate limits
- Local disk performance
- Number of unchanged files (cache effectiveness)
