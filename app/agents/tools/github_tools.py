"""
GitHub Tools - Production-grade GitHub API integration
Provides tools for agents to interact with GitHub
"""

import logging
from typing import Any, Dict, List, Optional
from github import Github, GithubException
import base64

logger = logging.getLogger(__name__)


class GitHubTools:
    """
    GitHub API integration for agent tools
    
    Provides both read and write operations on GitHub repos/PRs
    """
    
    def __init__(self, token: str):
        """Initialize GitHub client"""
        self.github = Github(token)
        self.user = self.github.get_user()
        logger.info(f"GitHub client initialized for user: {self.user.login}")
    
    # ========== READ OPERATIONS ==========
    
    async def get_pr_details(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a pull request
        
        Returns:
            PR details including title, description, author, status, etc.
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            return {
                "number": pr.number,
                "title": pr.title,
                "description": pr.body or "",
                "author": pr.user.login,
                "state": pr.state,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "base_branch": pr.base.ref,
                "head_branch": pr.head.ref,
                "mergeable": pr.mergeable,
                "mergeable_state": pr.mergeable_state,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "url": pr.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to get PR details: {e}")
            raise
    
    async def get_pr_files(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
    ) -> List[Dict[str, Any]]:
        """
        Get list of files changed in a PR
        
        Returns:
            List of files with their changes
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            files = []
            for file in pr.get_files():
                files.append({
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "patch": file.patch,
                    "sha": file.sha,
                })
            
            return files
        except GithubException as e:
            logger.error(f"Failed to get PR files: {e}")
            raise
    
    async def get_file_content(
        self,
        repo_owner: str,
        repo_name: str,
        file_path: str,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get content of a specific file
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            file_path: Path to file
            ref: Branch/commit ref (default: default branch)
            
        Returns:
            File content and metadata
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            
            if ref:
                content = repo.get_contents(file_path, ref=ref)
            else:
                content = repo.get_contents(file_path)
            
            # Decode content
            decoded_content = base64.b64decode(content.content).decode('utf-8')
            
            return {
                "path": content.path,
                "content": decoded_content,
                "sha": content.sha,
                "size": content.size,
                "encoding": content.encoding,
            }
        except GithubException as e:
            logger.error(f"Failed to get file content: {e}")
            raise
    
    async def get_pr_diff(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
    ) -> str:
        """
        Get full diff for a PR
        
        Returns:
            Complete diff as string
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            # Get diff from GitHub API
            # Note: This is a simplified version
            files = pr.get_files()
            
            diff_parts = []
            for file in files:
                if file.patch:
                    diff_parts.append(f"--- a/{file.filename}")
                    diff_parts.append(f"+++ b/{file.filename}")
                    diff_parts.append(file.patch)
                    diff_parts.append("")
            
            return "\n".join(diff_parts)
        except GithubException as e:
            logger.error(f"Failed to get PR diff: {e}")
            raise
    
    async def search_code(
        self,
        repo_owner: str,
        repo_name: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """
        Search code in repository
        
        Args:
            query: Search query
            
        Returns:
            List of matching code snippets
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            
            # Search code
            results = self.github.search_code(
                query=f"{query} repo:{repo_owner}/{repo_name}"
            )
            
            snippets = []
            for item in results[:10]:  # Limit to 10 results
                snippets.append({
                    "path": item.path,
                    "name": item.name,
                    "url": item.html_url,
                })
            
            return snippets
        except GithubException as e:
            logger.error(f"Failed to search code: {e}")
            raise
    
    # ========== WRITE OPERATIONS ==========
    
    async def post_review_comment(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        body: str,
    ) -> Dict[str, Any]:
        """
        Post a general comment on the PR (not tied to specific code line)
        Required params: body (comment text)
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            comment = pr.create_issue_comment(body)
            
            return {
                "id": comment.id,
                "body": comment.body,
                "created_at": comment.created_at.isoformat(),
                "url": comment.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to post comment: {e}")
            raise
    
    async def post_inline_comment(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        body: str,
        commit_id: str,
        path: str,
        line: int,
    ) -> Dict[str, Any]:
        """
        Post a review comment on a specific line of code in a PR
        Required params: body (comment text), commit_id (commit SHA), path (file path), line (line number)
            
        Returns:
            Created comment details
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            comment = pr.create_review_comment(
                body=body,
                commit=repo.get_commit(commit_id),
                path=path,
                line=line,
            )
            
            return {
                "id": comment.id,
                "body": comment.body,
                "path": comment.path,
                "line": comment.line,
                "created_at": comment.created_at.isoformat(),
            }
        except GithubException as e:
            logger.error(f"Failed to post inline comment: {e}")
            raise
    
    async def submit_review(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        event: str,  # "APPROVE", "REQUEST_CHANGES", "COMMENT"
        body: str,
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Submit a formal PR review with verdict
        Required params: event (APPROVE/REQUEST_CHANGES/COMMENT), body (review summary)
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            # Build review comments
            review_comments = []
            if comments:
                for comment in comments:
                    review_comments.append({
                        "path": comment["path"],
                        "line": comment["line"],
                        "body": comment["body"],
                    })
            
            # Create review
            review = pr.create_review(
                body=body,
                event=event,
                comments=review_comments if review_comments else None,
            )
            
            return {
                "id": review.id,
                "state": review.state,
                "body": review.body,
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            }
        except GithubException as e:
            logger.error(f"Failed to submit review: {e}")
            raise
    
    async def approve_pr(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        message: str = "LGTM! Code looks good. ✅",
    ) -> Dict[str, Any]:
        """
        Approve the PR (use when code is good and meets standards)
        Optional params: message (approval message)
        """
        return await self.submit_review(
            repo_owner=repo_owner,
            repo_name=repo_name,
            pr_number=pr_number,
            event="APPROVE",
            body=message,
        )
    
    async def request_changes(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        message: str,
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Request changes on a PR (use when issues must be fixed before merging)
        Required params: message (explanation of what needs to change)
        """
        return await self.submit_review(
            repo_owner=repo_owner,
            repo_name=repo_name,
            pr_number=pr_number,
            event="REQUEST_CHANGES",
            body=message,
            comments=comments,
        )
    
    async def create_commit(
        self,
        repo_owner: str,
        repo_name: str,
        branch: str,
        message: str,
        files: Dict[str, str],  # path -> content
    ) -> Dict[str, Any]:
        """
        Create a new commit with file changes
        
        Args:
            branch: Target branch
            message: Commit message
            files: Dict of file paths to new content
            
        Returns:
            Commit details
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            
            # Get current commit
            ref = repo.get_git_ref(f"heads/{branch}")
            latest_commit = repo.get_commit(ref.object.sha)
            base_tree = latest_commit.commit.tree
            
            # Create blobs for new files
            tree_elements = []
            for file_path, content in files.items():
                blob = repo.create_git_blob(content, "utf-8")
                tree_elements.append({
                    "path": file_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob.sha,
                })
            
            # Create tree
            tree = repo.create_git_tree(tree_elements, base_tree)
            
            # Create commit
            commit = repo.create_git_commit(
                message=message,
                tree=tree,
                parents=[latest_commit.commit],
            )
            
            # Update reference
            ref.edit(commit.sha)
            
            return {
                "sha": commit.sha,
                "message": commit.message,
                "url": commit.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to create commit: {e}")
            raise
    
    async def create_issue(
        self,
        repo_owner: str,
        repo_name: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new issue
        
        Args:
            title: Issue title
            body: Issue description
            labels: List of label names
            
        Returns:
            Created issue details
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=labels or [],
            )
            
            return {
                "number": issue.number,
                "title": issue.title,
                "url": issue.html_url,
                "state": issue.state,
            }
        except GithubException as e:
            logger.error(f"Failed to create issue: {e}")
            raise
    
    async def merge_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        merge_method: str = "merge",  # "merge", "squash", "rebase"
    ) -> Dict[str, Any]:
        """
        Merge a pull request
        
        Args:
            commit_title: Custom merge commit title
            merge_method: How to merge (merge/squash/rebase)
            
        Returns:
            Merge details
        """
        try:
            repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            
            result = pr.merge(
                commit_title=commit_title,
                merge_method=merge_method,
            )
            
            return {
                "merged": result.merged,
                "sha": result.sha,
                "message": result.message,
            }
        except GithubException as e:
            logger.error(f"Failed to merge PR: {e}")
            raise
