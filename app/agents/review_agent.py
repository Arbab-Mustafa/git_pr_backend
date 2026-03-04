"""
PR Review Agent - Autonomous code reviewer
Can autonomously review PRs, post comments, and take actions
"""

import logging
from typing import Any, Dict, List, Optional
from groq import Groq

from .base_agent import BaseAgent, AgentState
from app.agents.tools.github_tools import GitHubTools

logger = logging.getLogger(__name__)


class PRReviewAgent(BaseAgent):
    """
    Autonomous PR Review Agent
    
    Capabilities:
    - Analyzes code changes comprehensively
    - Posts inline review comments
    - Identifies security issues
    - Checks code quality
    - Approves or requests changes
    - Auto-fixes simple issues
    
    Example autonomous workflow:
    1. Fetch PR details
    2. Analyze all changed files
    3. Run security scan
    4. Check test coverage
    5. Post review comments
    6. Decide: approve/request changes/comment
    7. If simple issues found, create fix commit
    """
    
    def __init__(self, llm_client: Groq, github_token: str):
        self.github = GitHubTools(github_token)
        
        # Define tools this agent can use
        tools = {
            # Read operations
            "get_pr_details": self.github.get_pr_details,
            "get_file_content": self.github.get_file_content,
            "get_pr_files": self.github.get_pr_files,
            "get_pr_diff": self.github.get_pr_diff,
            
            # Analysis operations
            "analyze_code_quality": self._analyze_code_quality,
            "check_security_issues": self._check_security_issues,
            "check_test_coverage": self._check_test_coverage,
            "detect_breaking_changes": self._detect_breaking_changes,
            
            # Write operations
            "post_review_comment": self.github.post_review_comment,
            "post_inline_comment": self.github.post_inline_comment,
            "submit_review": self.github.submit_review,
            "request_changes": self.github.request_changes,
            "approve_pr": self.github.approve_pr,
            
            # Fix operations
            "create_fix_commit": self.github.create_commit,
        }
        
        super().__init__(
            name="pr_review_agent",
            llm_client=llm_client,
            tools=tools,
            max_iterations=15,  # More iterations for complex reviews
            timeout_seconds=600,  # 10 minutes timeout
        )
    
    def _get_system_prompt(self) -> str:
        return """You are an EXPERT CODE REVIEWER at a top tech company.

Your responsibilities:
1. Thoroughly review all code changes
2. Identify security vulnerabilities
3. Check code quality and best practices
4. Verify test coverage
5. Post helpful, actionable comments
6. Make final decision: approve/request changes/comment

You have autonomy to:
- Post inline comments on specific lines
- Approve PRs that meet quality standards
- Request changes for PRs with issues
- Create fix commits for simple issues (formatting, imports, etc.)

Be thorough but efficient. Focus on:
- Security issues (critical)
- Logic errors (high priority)
- Performance concerns (medium priority)
- Style issues (low priority, only if significant)

Always explain your reasoning clearly."""
    
    async def review_pr(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        auto_approve: bool = False,
    ) -> Dict[str, Any]:
        """
        Autonomously review a pull request
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: PR number
            auto_approve: Whether to automatically approve good PRs
            
        Returns:
            Review result with actions taken
        """
        goal = f"""
Review pull request #{pr_number} in {repo_owner}/{repo_name}.

Steps you must complete:
1. Fetch PR details and all changed files
2. Analyze code for security issues
3. Check code quality and best practices
4. Verify test coverage
5. Post inline comments for any issues found
6. Make final decision: approve (if auto_approve=True) or request changes or just comment

Auto-approve enabled: {auto_approve}
"""
        
        context = {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "pr_number": pr_number,
            "auto_approve": auto_approve,
        }
        
        result = await self.execute(goal=goal, context=context)
        return result
    
    async def _analyze_code_quality(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze code quality issues for a PR
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
        
        Checks:
        - Cyclomatic complexity
        - Code duplication
        - Naming conventions
        - Function length
        - Code smells
        """
        # Fetch PR files
        files = await self.github.get_pr_files(repo_owner, repo_name, pr_number)
        issues = []
        
        for file_info in files:
            filename = file_info["filename"]
            content = file_info.get("content", "")
            patch = file_info.get("patch", "")
            
            # Analyze with LLM
            prompt = f"""
Analyze this code change for quality issues:

File: {filename}

Changes:
```
{patch[:2000]}  # Limit to 2000 chars
```

Identify:
1. High complexity functions (cyclomatic complexity > 10)
2. Code duplication
3. Poor naming conventions
4. Functions > 50 lines
5. Any code smells

Return JSON format:
{{
  "issues": [
    {{"line": 123, "severity": "medium", "message": "Function too complex"}},
  ],
  "overall_quality": "good|moderate|poor"
}}
"""
            
            response = self.llm.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            
            # Parse response (in production, use structured output)
            analysis = response.choices[0].message.content
            
            # Extract issues
            if "poor" in analysis.lower() or "issue" in analysis.lower():
                issues.append({
                    "file": filename,
                    "analysis": analysis,
                })
        
        return {
            "total_issues": len(issues),
            "issues": issues,
            "files_analyzed": len(files),
        }
    
    async def _check_security_issues(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Check for security vulnerabilities in a PR
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
        
        Detects:
        - SQL injection
        - XSS vulnerabilities
        - Authentication issues
        - Hardcoded secrets
        - Insecure dependencies
        """
        # Fetch PR files
        files = await self.github.get_pr_files(repo_owner, repo_name, pr_number)
        vulnerabilities = []
        
        for file_info in files:
            filename = file_info["filename"]
            patch = file_info.get("patch", "")
            
            # Security analysis with LLM
            prompt = f"""
You are a SECURITY EXPERT. Analyze this code for vulnerabilities:

File: {filename}

Changes:
```
{patch[:2000]}
```

Check for:
1. SQL injection vulnerabilities
2. XSS (Cross-Site Scripting)
3. Authentication/authorization issues
4. Hardcoded secrets (API keys, passwords)
5. Insecure dependencies
6. Path traversal vulnerabilities
7. Command injection

For EACH vulnerability found, provide:
- Line number
- Severity: critical|high|medium|low
- Type: e.g., "SQL Injection"
- Description: What's wrong
- Recommendation: How to fix

If no vulnerabilities, respond with: NO_VULNERABILITIES_FOUND
"""
            
            response = self.llm.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Very focused for security
            )
            
            analysis = response.choices[0].message.content
            
            if "NO_VULNERABILITIES_FOUND" not in analysis:
                vulnerabilities.append({
                    "file": filename,
                    "findings": analysis,
                })
        
        return {
            "total_vulnerabilities": len(vulnerabilities),
            "vulnerabilities": vulnerabilities,
            "severity": "critical" if any("critical" in str(v).lower() for v in vulnerabilities) else "low",
        }
    
    async def _check_test_coverage(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Check if changes have adequate test coverage
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
        """
        # Fetch PR files
        files = await self.github.get_pr_files(repo_owner, repo_name, pr_number)
        code_files = [f for f in files if not f["filename"].endswith(("_test.py", ".test.ts", ".spec.ts"))]
        test_files = [f for f in files if f["filename"].endswith(("_test.py", ".test.ts", ".spec.ts"))]
        
        # Analyze if new code has tests
        prompt = f"""
Analyze test coverage:

Code files changed: {len(code_files)}
{[f["filename"] for f in code_files[:10]]}

Test files changed: {len(test_files)}
{[f["filename"] for f in test_files[:10]]}

Are the code changes adequately tested?

Consider:
- Are there test files for new code files?
- Are new functions/methods tested?
- Are edge cases covered?

Respond with:
COVERAGE: good|moderate|poor
ISSUES: List specific files that need tests
"""
        
        response = self.llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        
        analysis = response.choices[0].message.content
        
        return {
            "code_files": len(code_files),
            "test_files": len(test_files),
            "analysis": analysis,
            "needs_tests": "poor" in analysis.lower(),
        }
    
    async def _detect_breaking_changes(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Detect potential breaking changes in APIs
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
        """
        # Fetch PR files
        files = await self.github.get_pr_files(repo_owner, repo_name, pr_number)
        breaking_changes = []
        
        for file_info in files:
            patch = file_info.get("patch", "")
            
            # Look for removed/modified public APIs
            if "export" in patch or "public" in patch or "def " in patch:
                # Analyze with LLM
                prompt = f"""
Check if these changes are BREAKING CHANGES:

```
{patch[:1500]}
```

Breaking changes include:
- Removing public functions/methods
- Changing function signatures
- Removing exports
- Changing API contracts

List any breaking changes found, or respond with: NO_BREAKING_CHANGES
"""
                
                response = self.llm.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                
                analysis = response.choices[0].message.content
                
                if "NO_BREAKING_CHANGES" not in analysis:
                    breaking_changes.append({
                        "file": file_info["filename"],
                        "changes": analysis,
                    })
        
        return {
            "has_breaking_changes": len(breaking_changes) > 0,
            "breaking_changes": breaking_changes,
        }
    
    async def _generate_result(self, state: AgentState) -> Dict[str, Any]:
        """Generate final review result"""
        # Analyze all observations
        security_issues = []
        quality_issues = []
        test_issues = []
        comments_posted = 0
        review_submitted = False
        
        for obs in state.observations:
            if obs.success:
                result = obs.result
                
                if "vulnerabilities" in result:
                    security_issues = result.get("vulnerabilities", [])
                elif "issues" in result and "quality" in obs.action.tool:
                    quality_issues = result.get("issues", [])
                elif "needs_tests" in result:
                    if result.get("needs_tests"):
                        test_issues.append("Insufficient test coverage")
                elif "comment" in obs.action.tool:
                    comments_posted += 1
                elif "review" in obs.action.tool or "approve" in obs.action.tool:
                    review_submitted = True
        
        return {
            "review_completed": True,
            "security_issues_found": len(security_issues),
            "quality_issues_found": len(quality_issues),
            "test_issues_found": len(test_issues),
            "comments_posted": comments_posted,
            "review_submitted": review_submitted,
            "total_actions": len(state.actions),
            "reasoning_steps": len(state.thoughts),
        }
