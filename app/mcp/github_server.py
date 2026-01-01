import os
import subprocess
from github import Github
from github import GithubException
from mcp.server.fastmcp import FastMCP
from app.utils.logger import get_logger
from app.utils.config import GITHUB_TOKEN

logger = get_logger("github-mcp", "github_mcp.log")

mcp = FastMCP("GitHub")

WORKDIR = "/tmp/mcp-github"
os.makedirs(WORKDIR, exist_ok=True)

# -------------------------
# CLONE REPO
# -------------------------
@mcp.tool()
def clone_repo(repo: str) -> str:
    """
    Clone a GitHub repository locally.
    """
    logger.info(f"Cloning repo {repo}")

    repo_name = repo.split("/")[-1]
    repo_path = os.path.join(WORKDIR, repo_name)

    if os.path.exists(repo_path):
        logger.info("Repo already cloned; refreshing and checking out default branch")

        # Determine the default branch from origin/HEAD
        head_ref = subprocess.check_output(
            ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
            text=True,
        ).strip()
        default_branch = head_ref.split("/")[-1] if head_ref else "main"

        subprocess.run(["git", "-C", repo_path, "fetch", "--all", "--prune"], check=True)
        subprocess.run(["git", "-C", repo_path, "checkout", default_branch], check=True)
        subprocess.run(["git", "-C", repo_path, "pull", "--ff-only"], check=True)
        return repo_path

    clone_url = f"https://{GITHUB_TOKEN}@github.com/{repo}.git"
    subprocess.run(
        ["git", "clone", clone_url, repo_path],
        check=True,
    )

    return repo_path

# -------------------------
# CREATE BRANCH
# -------------------------
@mcp.tool()
def create_branch(repo_path: str, branch: str) -> str:
    """
    Create and checkout a new git branch.
    """
    logger.info(f"Creating branch {branch} in {repo_path}")

    # If branch already exists locally, just check it out.
    branch_exists = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "--verify", f"refs/heads/{branch}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0

    if branch_exists:
        subprocess.run(
            ["git", "-C", repo_path, "checkout", branch],
            check=True,
        )
    else:
        subprocess.run(
            ["git", "-C", repo_path, "checkout", "-b", branch],
            check=True,
        )

    return branch


# -------------------------
# PUSH BRANCH
# -------------------------
@mcp.tool()
def push_branch(repo_path: str, branch: str) -> str:
    """
    Push a branch to origin so it exists remotely for PR creation.
    """
    logger.info(f"Pushing branch {branch} from {repo_path}")

    subprocess.run(
        ["git", "-C", repo_path, "push", "-u", "origin", branch],
        check=True,
    )

    return branch

# -------------------------
# COMMIT CHANGES
# -------------------------
@mcp.tool()
def commit_changes(
    repo_path: str,
    message: str
) -> str:
    """
    Commit all changes in repo.
    """
    logger.info(f"Committing changes in {repo_path}")

    subprocess.run(
        ["git", "-C", repo_path, "add", "."],
        check=True,
    )
    subprocess.run(
        ["git", "-C", repo_path, "commit", "-m", message],
        check=True,
    )

    return message

# -------------------------
# CREATE PULL REQUEST
# -------------------------
@mcp.tool()
def create_pull_request(
    repo: str,
    branch: str,
    title: str,
    body: str,
) -> str:
    """
    Create a pull request.
    """
    logger.info(f"Creating PR for repo={repo}, branch={branch}")

    gh = Github(GITHUB_TOKEN)
    try:
        repository = gh.get_repo(repo)

        pr = repository.create_pull(
            title=title,
            body=body,
            head=branch,
            base="main",
        )
    except GithubException as e:
        status = getattr(e, "status", None)
        data = getattr(e, "data", None)
        logger.error(
            f"GitHub API error while creating PR for repo={repo}, branch={branch}: "
            f"status={status}, data={data}",
            exc_info=True,
        )
        if status == 403:
            raise ValueError(
                "GitHub rejected the request (403). Your `GITHUB_TOKEN` does not have access to create PRs "
                f"in `{repo}`. Ensure the token has repo access and PR write permissions (classic PAT: `repo` scope; "
                "fine-grained PAT: Repo access + Pull requests: Read & write). If the repo is in an org with SAML SSO, "
                "authorize the token for SSO."
            )
        raise

    return pr.html_url

if __name__ == "__main__":
    logger.info("Starting GitHub MCP server (stdio)")
    mcp.run(transport="stdio")
