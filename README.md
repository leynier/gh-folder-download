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

```bash
Usage: gh-folder-download [OPTIONS]

Options:
  --url TEXT                      Repository URL  [required]
  --output DIRECTORY              Output folder  [default: .]
  --token TEXT                    GitHub token
  --force / --no-force            Remove existing output folder if it exists
                                  [default: no-force]
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```
