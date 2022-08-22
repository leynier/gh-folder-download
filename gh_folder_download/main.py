from os import makedirs
from os.path import exists, join
from pathlib import Path
from shutil import rmtree
from typing import Optional, Union

from github import Github, GithubException
from github.ContentFile import ContentFile
from github.Repository import Repository
from rich import print
from typer import Option, Typer
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
    Download all contents at server_path with commit tag sha in
    the repository.
    """
    fullpath = join(output, path)
    if exists(fullpath):
        if force:
            rmtree(fullpath)
        else:
            print("Output folder already exists")
            return
    makedirs(fullpath)
    contents = repository.get_dir_contents(path, ref=sha)
    for content in contents:
        print(f"Downloading {content.path}")
        fullpath = join(output, content.path)
        if content.type == "dir":
            makedirs(fullpath)
            download_folder(repository, sha, content.path, output, force)
        else:
            try:
                file_content = repository.get_contents(content.path, ref=sha)
                if not isinstance(file_content, ContentFile):
                    raise ValueError("Expected ContentFile")
                wget_download(file_content.download_url, fullpath)
                print("")
            except (GithubException, OSError, ValueError) as exc:
                print("Error processing %s: %s", content.path, exc)
