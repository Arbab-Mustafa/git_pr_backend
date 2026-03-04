"""
New agent-powered endpoints for FastAPI
Integrates autonomous agents with existing API
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.agents import AgentOrchestrator, TaskType
from app.config import settings
from groq import Groq

router = APIRouter(prefix="/agent", tags=["AI Agent"])

# Global orchestrator instance (in production, use dependency injection)
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Dependency: Get agent orchestrator instance"""
    global _orchestrator
    
    if _orchestrator is None:
        llm = Groq(api_key=settings.GROQ_API_KEY)
        _orchestrator = AgentOrchestrator(
            llm_client=llm,
            github_token=settings.GITHUB_TOKEN,
            max_concurrent_agents=settings.MAX_CONCURRENT_AGENTS,
        )
    
    return _orchestrator


# ========== Request/Response Models ==========

class AgentReviewRequest(BaseModel):
    """Request for autonomous PR review"""
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    pr_number: int = Field(..., description="Pull request number")
    auto_approve: bool = Field(default=False, description="Allow auto-approval")
    priority: int = Field(default=5, ge=1, le=10, description="Task priority (1-10)")


class AgentTaskResponse(BaseModel):
    """Response for submitted agent task"""
    task_id: str
    status: str
    message: str


class AgentTaskStatusResponse(BaseModel):
    """Agent task status response"""
    task_id: str
    status: str
    submitted_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Dict[str, Any]]
    error: Optional[str]


class OrchestratorStatusResponse(BaseModel):
    """Orchestrator system status"""
    registered_agents: List[str]
    queue_length: int
    active_tasks: int
    completed_tasks: int
    max_concurrent: int
    memory_stats: Dict[str, Any]


# ========== Endpoints ==========

@router.post("/review-pr", response_model=AgentTaskResponse)
async def autonomous_pr_review(
    request: AgentReviewRequest,
    background_tasks: BackgroundTasks,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🤖 Autonomous PR Review
    
    Submits a PR for autonomous review by AI agent.
    
    The agent will:
    - Fetch and analyze all PR changes
    - Run security scans
    - Check code quality
    - Verify test coverage
    - Post inline comments
    - Approve or request changes
    
    Returns immediately with task_id. Use /task-status to check progress.
    
    **Example:**
    ```json
    {
      "repo_owner": "microsoft",
      "repo_name": "vscode",
      "pr_number": 12345,
      "auto_approve": false,
      "priority": 8
    }
    ```
    """
    try:
        # Submit task to orchestrator
        task_id = await orchestrator.submit_task(
            task_type=TaskType.PR_REVIEW,
            parameters={
                "repo_owner": request.repo_owner,
                "repo_name": request.repo_name,
                "pr_number": request.pr_number,
                "auto_approve": request.auto_approve,
            },
            priority=request.priority,
        )
        
        return AgentTaskResponse(
            task_id=task_id,
            status="submitted",
            message=f"PR review task submitted. Agent will autonomously review PR #{request.pr_number}",
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.post("/review-pr-sync", response_model=Dict[str, Any])
async def autonomous_pr_review_sync(
    request: AgentReviewRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🤖 Autonomous PR Review (Synchronous)
    
    Same as /review-pr but waits for completion before returning.
    
    ⚠️ Warning: This can take 1-5 minutes depending on PR size.
    Use /review-pr for async operation in production.
    
    Returns complete review result.
    """
    try:
        # Execute task synchronously
        result = await orchestrator.execute_task(
            task_type=TaskType.PR_REVIEW,
            parameters={
                "repo_owner": request.repo_owner,
                "repo_name": request.repo_name,
                "pr_number": request.pr_number,
                "auto_approve": request.auto_approve,
            },
        )
        
        return {
            "success": result.success,
            "result": result.result,
            "reasoning_steps": len(result.reasoning_chain),
            "actions_taken": len(result.actions_taken),
            "execution_time": result.execution_time_seconds,
            "iterations": result.total_iterations,
            "error": result.error,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")


@router.get("/task-status/{task_id}", response_model=AgentTaskStatusResponse)
async def get_task_status(
    task_id: str,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    📊 Get Agent Task Status
    
    Check status of a submitted agent task.
    
    Statuses:
    - `pending`: In queue, not started
    - `in_progress`: Currently being processed
    - `completed`: Successfully completed
    - `failed`: Failed with error
    """
    task = orchestrator._get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    response = AgentTaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        submitted_at=task.created_at.isoformat(),
        completed_at=None,
        result=None,
        error=None,
    )
    
    if task.result:
        response.completed_at = task.result.metadata.get("completed_at")
        if task.result.success:
            response.result = task.result.result
        else:
            response.error = task.result.error
    
    return response


@router.get("/status", response_model=OrchestratorStatusResponse)
async def get_orchestrator_status(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🎭 Orchestrator Status
    
    Get current status of the agent orchestration system.
    
    Shows:
    - Available agents
    - Task queue length
    - Active tasks
    - Memory statistics
    """
    status = orchestrator.get_status()
    memory_stats = orchestrator.memory.get_stats()
    
    return OrchestratorStatusResponse(
        registered_agents=status["registered_agents"],
        queue_length=status["queue_length"],
        active_tasks=status["active_tasks"],
        completed_tasks=status["completed_tasks"],
        max_concurrent=status["max_concurrent"],
        memory_stats=memory_stats,
    )


@router.post("/webhook/github")
async def github_webhook(
    request: dict,
    background_tasks: BackgroundTasks,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🔔 GitHub Webhook Handler
    
    Receives GitHub webhook events and automatically triggers agents.
    
    Events handled:
    - `pull_request` (opened, synchronize) → Auto-review
    - `workflow_run` (failure) → Auto-diagnose
    
    Configure webhook in GitHub:
    1. Settings → Webhooks → Add webhook
    2. URL: https://your-domain.com/agent/webhook/github
    3. Content type: application/json
    4. Events: Pull requests, Workflow runs
    """
    # In production, validate webhook signature here
    
    event_type = request.get("type", "unknown")
    
    # Process webhook in background
    background_tasks.add_task(
        orchestrator.handle_webhook,
        event_type,
        request,
    )
    
    return {"status": "received"}


@router.get("/memory/patterns")
async def get_learned_patterns(
    pattern_type: Optional[str] = None,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🧠 View Learned Patterns
    
    See patterns the agent has learned from past executions.
    
    This shows the agent's "knowledge base" accumulated over time.
    """
    if pattern_type:
        patterns = await orchestrator.memory.semantic.search_patterns(
            query=pattern_type,
            limit=20,
        )
    else:
        patterns = await orchestrator.memory.semantic.get_all_patterns()
    
    return {
        "patterns": patterns,
        "total": len(patterns),
    }


@router.get("/memory/history")
async def get_task_history(
    task_type: Optional[str] = None,
    limit: int = 50,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    📜 Task Execution History
    
    View history of completed agent tasks.
    
    Useful for:
    - Debugging agent behavior
    - Analyzing success rate
    - Understanding agent decisions
    """
    episodes = await orchestrator.memory.episodic.retrieve_episodes(
        task_type=task_type,
        limit=limit,
    )
    
    # Calculate stats
    total = len(episodes)
    successful = sum(1 for ep in episodes if ep.get("success"))
    success_rate = (successful / total * 100) if total > 0 else 0
    
    return {
        "episodes": episodes,
        "total": total,
        "successful": successful,
        "success_rate": f"{success_rate:.1f}%",
    }


@router.delete("/memory/clear")
async def clear_working_memory(
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
):
    """
    🗑️ Clear Working Memory
    
    Clears temporary working memory (not long-term learnings).
    
    Use this to free up memory if needed.
    """
    await orchestrator.memory.working.clear()
    
    return {
        "status": "cleared",
        "message": "Working memory cleared",
    }
