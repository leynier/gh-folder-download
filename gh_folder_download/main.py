import os
from os import makedirs
from os.path import exists, join
from pathlib import Path
from shutil import rmtree
from typing import Optional, Union

from github import Github, GithubException
from github.ContentFile import ContentFile
from github.Repository import Repository
from rich import print
from typer import Option, Typer, confirm
from wget import download as wget_download

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
) -> None:
    """
    Downloads a repository from a given URL and saves it to the specified output folder.

    Args:
        url (str): The URL of the repository to download.
        output (Path): The folder where the repository will be saved.
        token (Optional[str]): The GitHub token to access private repositories.
        force (bool): Whether to remove the existing output folder if it already exists.

    Returns:
        None
    """
    org, repo, branch, path = parse_github_url(url)
    github = Github(token)
    repository = github.get_repo(f"{org}/{repo}")
    if not branch:
        branch = repository.default_branch
    sha = get_sha_for_branch_or_tag(repository, branch)
    download_folder(repository, sha, path, output, force)


def parse_github_url(url: str) -> tuple[str, str, Union[str, None], str]:
    """
    Parses a GitHub repo url and returns the owner, repo, branch and path.
    """
    if not url.startswith("https://github.com/"):
        raise ValueError("Invalid GitHub URL")
    url = url.replace("https://github.com/", "")
    if url.endswith(".git"):
        url = url[:-4]
    segments = url.split("/")
    segments_count = len(segments)
    if segments_count < 2 or segments_count == 3:
        raise ValueError("Invalid GitHub URL")
    org = segments[0]
    repo = segments[1]
    if segments_count == 2:
        branch = None
        path = ""
    else:
        branch = segments[3]
        path = "/".join(segments[4:])
    return org, repo, branch, path


def get_sha_for_branch_or_tag(repository: Repository, branch_or_tag: str) -> str:
    """
    Returns a commit PyGithub object for the specified repository and branch or tag.
    """
    branches = repository.get_branches()
    matched_branches = [match for match in branches if match.name == branch_or_tag]
    if matched_branches:
        return matched_branches[0].commit.sha
    tags = repository.get_tags()
    matched_tags = [match for match in tags if match.name == branch_or_tag]
    if not matched_tags:
        raise ValueError("No Tag or Branch exists with that name")
    return matched_tags[0].commit.sha


def download_folder(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
) -> None:
    """
    Downloads a folder from a repository.

    Args:
        repository (Repository): The repository to download from.
        sha (str): The SHA of the commit or tree to download.
        path (str): The path of the folder to download.
        output (Path): The output path where the folder will be saved.
        force (bool): If True, existing folder will be removed before downloading.

    Returns:
        None: This function does not return anything.
    """
    fullpath = join(output, path)
    existing_items = set(os.listdir(fullpath)) if os.path.exists(fullpath) else set()

    # Get contents of the folder and assign to extra_items
    contents = repository.get_dir_contents(path, ref=sha)
    github_items = {content.name for content in contents}
    extra_items = existing_items - github_items

    if exists(fullpath):
        if extra_items:
            # Display confirmation prompt
            if confirm(
                f"Folder contains extra items: {extra_items}. Do you want to continue?"
            ):
                rmtree(fullpath)
            else:
                print("Operation cancelled.")
                return
        elif force:
            rmtree(fullpath)
        else:
            print("Output folder already exists")
            return

    makedirs(fullpath)
    contents = repository.get_dir_contents(path, ref=sha)

    # Separate files and directories
    files = [content for content in contents if content.type == "file"]
    directories = [content for content in contents if content.type == "dir"]

    # First, download all files in the current folder
    for file_content in files:
        print(f"Downloading {file_content.path}")
        fullpath = join(output, file_content.path)
        try:
            file_data = repository.get_contents(file_content.path, ref=sha)
            if not isinstance(file_data, ContentFile):
                raise ValueError("Expected ContentFile")
            wget_download(file_data.download_url, fullpath)
            print("")
        except (GithubException, OSError, ValueError) as exc:
            print(f"Error processing {file_content.path}: {exc}")

    # Then, download sub-directories
    for directory in directories:
        print(f"Downloading directory {directory.path}")
        download_folder(repository, sha, directory.path, output, force)
