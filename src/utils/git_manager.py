"""Git-based version control for composition projects.

Each composition project is a git repository that tracks
notation files, plans, and metadata (but not large renders).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_composition_repo(path: str) -> str:
    """Initialize a git repository for a composition project.

    Args:
        path: Directory to initialize.

    Returns:
        Path to the initialized repository.
    """
    import git

    repo_path = Path(path)
    repo_path.mkdir(parents=True, exist_ok=True)

    if (repo_path / ".git").exists():
        logger.info("Git repo already exists: %s", path)
        return path

    repo = git.Repo.init(path)

    # Create .gitignore for composition projects
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "renders/\noutput/\n*.wav\n*.mp3\n*.flac\n*.mid\n",
            encoding="utf-8",
        )

    # Initial commit
    repo.index.add([".gitignore"])
    repo.index.commit("Initialize composition project")
    logger.info("Initialized git repo: %s", path)
    return path


def commit(path: str, message: str) -> str:
    """Commit all tracked changes in a composition repository.

    Args:
        path: Path to the git repository.
        message: Commit message.

    Returns:
        Commit hash string.
    """
    import git

    repo = git.Repo(path)

    # Initialize if needed
    if not (Path(path) / ".git").exists():
        init_composition_repo(path)
        repo = git.Repo(path)

    # Stage all changes (respecting .gitignore)
    repo.git.add(A=True)

    if not repo.is_dirty() and not repo.untracked_files:
        logger.info("No changes to commit in %s", path)
        return ""

    commit_obj = repo.index.commit(message)
    commit_hash = str(commit_obj.hexsha[:8])
    logger.info("Committed %s: %s", commit_hash, message)
    return commit_hash


def branch(path: str, name: str) -> str:
    """Create a new branch in a composition repository.

    Args:
        path: Path to the git repository.
        name: Branch name.

    Returns:
        Branch name.
    """
    import git

    repo = git.Repo(path)
    new_branch = repo.create_head(name)
    new_branch.checkout()
    logger.info("Created and checked out branch: %s", name)
    return name


def diff(path: str) -> str:
    """Get the diff of uncommitted changes.

    Args:
        path: Path to the git repository.

    Returns:
        Diff string.
    """
    import git

    repo = git.Repo(path)
    return repo.git.diff()


def log(path: str, max_count: int = 10) -> list[dict[str, str]]:
    """Get recent commit history.

    Args:
        path: Path to the git repository.
        max_count: Maximum number of commits to return.

    Returns:
        List of commit dicts with hash, message, and date.
    """
    import git

    repo = git.Repo(path)
    commits = []
    for c in repo.iter_commits(max_count=max_count):
        commits.append({
            "hash": str(c.hexsha[:8]),
            "message": c.message.strip(),
            "date": str(c.committed_datetime),
        })
    return commits
