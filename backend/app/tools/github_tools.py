import os
from langchain_core.tools import tool
from github import Github
from github.GithubException import GithubException
import git

def _get_github_client() -> Github:
    """Helper to get an authenticated Github client."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set. Cannot use GitHub API.")
    return Github(token)

@tool
def create_github_issue(repo: str, title: str, body: str) -> str:
    """
    Create a new issue on GitHub.
    
    Args:
        repo: The repository name with owner, e.g., 'owner/repo'.
        title: The title of the issue.
        body: The markdown body content of the issue.
    """
    try:
        g = _get_github_client()
        repository = g.get_repo(repo)
        issue = repository.create_issue(title=title, body=body)
        return f"Successfully created issue #{issue.number}: {issue.html_url}"
    except Exception as e:
        return f"Failed to create issue: {str(e)}"

@tool
def create_github_pr(repo: str, title: str, body: str, head_branch: str, base_branch: str = "main") -> str:
    """
    Create a new Pull Request on GitHub.
    
    Args:
        repo: The repository name with owner, e.g., 'owner/repo'.
        title: The title of the pull request.
        body: The markdown body content of the pull request.
        head_branch: The name of the branch where your changes are implemented.
        base_branch: The name of the branch you want the changes pulled into. Default is 'main'.
    """
    try:
        g = _get_github_client()
        repository = g.get_repo(repo)
        pr = repository.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch
        )
        return f"Successfully created PR #{pr.number}: {pr.html_url}"
    except Exception as e:
        return f"Failed to create pull request: {str(e)}"

@tool
def commit_and_push(repo_path: str, branch_name: str, commit_message: str) -> str:
    """
    Create a new branch locally, switch to it, commit all tracked and untracked changes, and push it to the remote origin.
    
    Args:
        repo_path: The absolute path to the local git repository.
        branch_name: The name of the new branch to create.
        commit_message: The commit message for the changes.
    """
    try:
        if not os.path.exists(repo_path):
            return f"Error: Repository path '{repo_path}' does not exist."
            
        r = git.Repo(repo_path)
        if r.is_dirty(untracked_files=True):
            current = r.active_branch
            # Create new branch based on current branch
            new_branch = r.create_head(branch_name)
            new_branch.checkout()
            
            # Add all files including untracked
            r.git.add('.')
            r.index.commit(commit_message)
            
            # Push to origin
            origin = r.remote(name='origin')
            origin.push(refspec=f'{branch_name}:{branch_name}')
            
            # Switch back to original branch
            current.checkout()
            return f"Successfully committed and pushed to branch: {branch_name}"
        else:
            return "No changes to commit. Working tree is clean."
            
    except Exception as e:
        return f"Failed to commit and push: {str(e)}"
