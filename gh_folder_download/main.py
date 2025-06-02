from os import makedirs
from os.path import exists, join
from pathlib import Path
from shutil import rmtree
from time import time
from typing import Optional, Union

from github import Github, GithubException
from github.ContentFile import ContentFile
from github.Repository import Repository
from typer import Option, Typer

from .logger import get_logger, setup_logger

app = Typer()


@app.command()
def download_command(
    url: str = Option(..., help="Repository URL"),
    output: Path = Option(
        ".",
        help="Output folder",
        file_okay=False,
        writable=True,
    ),
    token: Optional[str] = Option(None, help="GitHub token"),
    force: bool = Option(False, help="Remove existing output folder if it exists"),
    verbose: bool = Option(False, "--verbose", "-v", help="Enable verbose logging"),
    quiet: bool = Option(False, "--quiet", "-q", help="Suppress output except errors"),
    log_file: Optional[Path] = Option(None, help="Log to file"),
) -> None:
    # Setup logging
    if quiet:
        log_level = "ERROR"
    elif verbose:
        log_level = "DEBUG"
    else:
        log_level = "INFO"

    logger = setup_logger(level=log_level, log_file=log_file, quiet=quiet)

    try:
        # Parse URL and setup
        org, repo, branch, path = parse_github_url(url)
        github = Github(token)
        repository = github.get_repo(f"{org}/{repo}")

        if not branch:
            branch = repository.default_branch

        # Display repository information
        logger.repository_info(org, repo, branch, path)

        # Get SHA for branch/tag
        logger.progress_info(f"Getting commit SHA for branch '{branch}'")
        sha = get_sha_for_branch_or_tag(repository, branch)
        logger.debug(f"Found SHA: {sha}")

        # Start download
        start_time = time()
        stats = download_folder(repository, sha, path, output, force)
        end_time = time()

        # Show summary
        if stats["total_files"] > 0:
            logger.summary(
                total_files=stats["total_files"],
                total_size=stats["total_size"],
                duration=end_time - start_time,
            )
        else:
            logger.warning("No files were downloaded")

    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        raise
    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


def parse_github_url(url: str) -> tuple[str, str, Union[str, None], str]:
    """
    Parses a GitHub repo url and returns the owner, repo, branch and path.
    """
    logger = get_logger()
    logger.debug(f"Parsing GitHub URL: {url}")

    if not url.startswith("https://github.com/"):
        raise ValueError("Invalid GitHub URL - must start with https://github.com/")

    url = url.replace("https://github.com/", "")
    if url.endswith(".git"):
        url = url[:-4]

    segments = url.split("/")
    segments_count = len(segments)

    if segments_count < 2 or segments_count == 3:
        raise ValueError("Invalid GitHub URL - must include owner and repository")

    org = segments[0]
    repo = segments[1]

    if segments_count == 2:
        branch = None
        path = ""
    else:
        if segments_count < 4 or segments[2] != "tree":
            raise ValueError("Invalid GitHub URL - tree path format is incorrect")
        branch = segments[3]
        path = "/".join(segments[4:])

    logger.debug(f"Parsed - Org: {org}, Repo: {repo}, Branch: {branch}, Path: {path}")
    return org, repo, branch, path


def get_sha_for_branch_or_tag(repository: Repository, branch_or_tag: str) -> str:
    """
    Returns a commit PyGithub object for the specified repository and branch or tag.
    """
    logger = get_logger()

    # Try branches first
    logger.debug(f"Looking for branch: {branch_or_tag}")
    branches = repository.get_branches()
    matched_branches = [match for match in branches if match.name == branch_or_tag]
    if matched_branches:
        logger.debug(f"Found branch: {branch_or_tag}")
        return matched_branches[0].commit.sha

    # Try tags
    logger.debug(f"Branch not found, looking for tag: {branch_or_tag}")
    tags = repository.get_tags()
    matched_tags = [match for match in tags if match.name == branch_or_tag]
    if matched_tags:
        logger.debug(f"Found tag: {branch_or_tag}")
        return matched_tags[0].commit.sha

    raise ValueError(
        f"No branch or tag named '{branch_or_tag}' exists in the repository"
    )


def download_folder(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
) -> dict[str, int]:
    """
    Download all contents at server_path with commit tag sha in
    the repository.

    Returns download statistics.
    """
    logger = get_logger()
    stats = {"total_files": 0, "total_size": 0}

    fullpath = join(output, path)

    if exists(fullpath):
        if force:
            logger.warning(f"Removing existing folder: {fullpath}")
            rmtree(fullpath)
        else:
            logger.error(f"Output folder already exists: {fullpath}")
            logger.info("Use --force to overwrite existing folders")
            return stats

    logger.progress_info(f"Creating directory: {fullpath}")
    makedirs(fullpath, exist_ok=True)

    try:
        logger.debug(f"Getting contents for path: {path}")
        contents = repository.get_dir_contents(path, ref=sha)
    except GithubException as e:
        logger.error(f"Failed to get directory contents for '{path}': {e}")
        return stats

    for content in contents:
        fullpath = join(output, content.path)

        if content.type == "dir":
            logger.debug(f"Found directory: {content.path}")
            makedirs(fullpath, exist_ok=True)
            # Recursively download subdirectory
            sub_stats = download_folder(repository, sha, content.path, output, force)
            stats["total_files"] += sub_stats["total_files"]
            stats["total_size"] += sub_stats["total_size"]
        else:
            # Download file
            try:
                logger.download_start(content.path, content.size)
                file_content = repository.get_contents(content.path, ref=sha)

                if not isinstance(file_content, ContentFile):
                    logger.error(f"Expected ContentFile for {content.path}")
                    continue

                if file_content.download_url is None:
                    logger.warning(f"No download URL available for {content.path}")
                    continue

                # Download the file
                import urllib.request

                urllib.request.urlretrieve(file_content.download_url, fullpath)

                stats["total_files"] += 1
                stats["total_size"] += content.size or 0

                logger.download_complete(content.path)

            except (GithubException, OSError, ValueError) as exc:
                logger.download_error(content.path, str(exc))

    return stats
