# GitHub Folder Downloader

## Contributions are highly appreciated

### All contributors will be granted credit on the following list

* Leynier Gutiérrez González ([@leynier](https://github.com/leynier))

You can help out by:

* Reporting a bug
* Reviewing the code
* Submitting a fix
* Proposing new features
* Becoming a maintainer

## Branches

We're using the following branches to manage work:

* `main` is the protected release branch
* Feature and bugfix work should use short-lived branches based on `main`

## How to report bugs

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/leynier/gh-folder-download/issues/new/choose); it's that easy!

### Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

* A quick summary and/or background
* Steps to reproduce
  * Be specific!
  * Give sample code if you can.
* What you expected to happen
* What actually happens
* Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

We <3 thorough bug reports.

## How to contribute code

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

Pull requests are the best way to propose changes to the codebase. We use a loose version of Git Flow
and actively welcome your pull requests:

1. Create a new branch based on `main`:
   * Feature branches should start with `feature/`
   * Bugfix branches should start with `bug/`
2. Implement your changes.
3. Add tests if applicable.
4. Run `make check`.
5. Issue that pull request!

The offline test suite measures every maintained `gh_folder_download` module and enforces 100% line coverage. A change
with an uncovered executable line fails `make check` and the GitHub Actions `checks` job.

### Security tooling

Use uv 0.13.5 or newer and run `make security` to audit all runtime and development dependencies from the locked, hashed export and scan application source with Bandit. The export includes transitive packages; `--disable-pip --require-hashes` prevents pip-audit from resolving or installing them again with pip. Package installation and builds use uv. pip-api can still invoke `pip --version` locally, with pip's version check disabled internally.

The dependency floors cover [certifi's eMudhra trust removal](https://github.com/advisories/GHSA-6q48-6c7w-9gw2), pip's independent certifi bundle, and filelock's patched development dependency. CI pins [uv 0.13.5](https://github.com/astral-sh/uv/releases/tag/0.13.5), which also rejects compromised intermediate keys and selects managed Python builds with patched bundled pip.

As of 2026-10-24, the latest upstream pip, 26.2.2, still vendors urllib3 2.7.0, affected by [GHSA-8988-9cw3-xx77](https://github.com/advisories/GHSA-8988-9cw3-xx77), [GHSA-gh4c-6fx4-qh6g](https://github.com/advisories/GHSA-gh4c-6fx4-qh6g), and [GHSA-vxq7-64xx-v4gw](https://github.com/advisories/GHSA-vxq7-64xx-v4gw). The project's standalone urllib3 is already 2.8.0 and does not replace pip's vendor. The configured audit avoids pip network operations; manually using this development environment's pip to contact package indexes retains that upstream risk until pip publishes an updated vendor. Do not edit installed vendor files or suppress these advisories. A clean lock audit does not audit pip's internal vendor or prove an existing installation or host trust store is patched.

### Any contributions you make will be under the MIT License

When you submit code changes, your submissions are understood to be under the same [MIT](LICENSE) that covers the project.
