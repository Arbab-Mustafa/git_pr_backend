"""
Agent Orchestrator - Coordinates multiple agents
Handles task routing, agent collaboration, and workflow management
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional, Type
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from .base_agent import BaseAgent, AgentResult
from .review_agent import PRReviewAgent
from app.agents.memory.agent_memory import AgentMemory

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of tasks the orchestrator can handle"""
    PR_REVIEW = "pr_review"
    TEST_GENERATION = "test_generation"
    SECURITY_SCAN = "security_scan"
    DOCUMENTATION = "documentation"
    CODE_REFACTORING = "code_refactoring"
    CI_CD_FIX = "ci_cd_fix"


@dataclass
class Task:
    """Represents a high-level task"""
    task_id: str
    task_type: TaskType
    priority: int  # 1-10, higher = more urgent
    parameters: Dict[str, Any]
    created_at: datetime
    assigned_agent: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[AgentResult] = None


class AgentOrchestrator:
    """
    Enterprise-grade multi-agent orchestration system
    
    Responsibilities:
    - Task queue management
    - Agent selection and routing
    - Multi-agent collaboration
    - Workflow coordination
    - Resource management
    - Error handling and recovery
    
    Architecture:
    
    User/System Request
            │
            ▼
    ┌──────────────────┐
    │  Orchestrator    │
    │  - Parse request │
    │  - Route task    │
    │  - Monitor       │
    └──────┬───────────┘
           │
           ├───► Review Agent
           ├───► Test Agent
           ├───► Security Agent
           └───► Custom Agents
    """
    
    def __init__(
        self,
        llm_client,
        github_token: str,
        max_concurrent_agents: int = 5,
    ):
        self.llm = llm_client
        self.github_token = github_token
        self.max_concurrent_agents = max_concurrent_agents
        
        # Initialize logger first
        self.logger = logging.getLogger("orchestrator")
        
        # Initialize memory system
        self.memory = AgentMemory()
        
        # Register available agents
        self.agents: Dict[str, BaseAgent] = {}
        self._register_agents()
        
        # Task management
        self.task_queue: List[Task] = []
        self.active_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []
        
        self.logger.info("🎭 Agent Orchestrator initialized")
    
    def _register_agents(self):
        """Register available agents"""
        # Review Agent
        review_agent = PRReviewAgent(
            llm_client=self.llm,
            github_token=self.github_token,
        )
        self.agents["pr_review"] = review_agent
        
        # Add more agents as they're implemented
        # self.agents["test_generation"] = TestGenerationAgent(...)
        # self.agents["security"] = SecurityAgent(...)
        
        self.logger.info(f"✓ Registered {len(self.agents)} agents")
    
    async def submit_task(
        self,
        task_type: TaskType,
        parameters: Dict[str, Any],
        priority: int = 5,
    ) -> str:
        """
        Submit a new task to the orchestrator
        
        Args:
            task_type: Type of task
            parameters: Task-specific parameters
            priority: Task priority (1-10)
            
        Returns:
            Task ID
        """
        task = Task(
            task_id=f"{task_type.value}_{int(datetime.utcnow().timestamp())}",
            task_type=task_type,
            priority=priority,
            parameters=parameters,
            created_at=datetime.utcnow(),
        )
        
        self.task_queue.append(task)
        self.task_queue.sort(key=lambda t: t.priority, reverse=True)
        
        self.logger.info(
            f"📝 Task submitted: {task.task_id} "
            f"(type: {task_type.value}, priority: {priority})"
        )
        
        # Auto-start processing if capacity available
        if len(self.active_tasks) < self.max_concurrent_agents:
            asyncio.create_task(self._process_next_task())
        
        return task.task_id
    
    async def execute_task(
        self,
        task_type: TaskType,
        parameters: Dict[str, Any],
    ) -> AgentResult:
        """
        Execute task synchronously (wait for completion)
        
        Args:
            task_type: Type of task
            parameters: Task parameters
            
        Returns:
            Agent execution result
        """
        task_id = await self.submit_task(task_type, parameters)
        
        # Wait for completion
        while True:
            task = self._get_task(task_id)
            if task and task.status in ["completed", "failed"]:
                return task.result
            await asyncio.sleep(1)
    
    async def _process_next_task(self):
        """Process next task from queue"""
        if not self.task_queue:
            return
        
        # Get highest priority task
        task = self.task_queue.pop(0)
        task.status = "in_progress"
        self.active_tasks[task.task_id] = task
        
        self.logger.info(f"🚀 Starting task: {task.task_id}")
        
        try:
            # Select appropriate agent
            agent = self._select_agent(task)
            task.assigned_agent = agent.name
            
            # Load relevant memory
            context = await self._load_task_context(task)
            task.parameters["context"] = context
            
            # Execute task with agent
            result = await self._execute_with_agent(agent, task)
            
            # Store result in memory
            await self._save_task_result(task, result)
            
            # Update task
            task.status = "completed"
            task.result = result
            
            self.logger.info(
                f"✅ Task completed: {task.task_id} "
                f"(agent: {agent.name}, success: {result.success})"
            )
            
        except Exception as e:
            self.logger.error(f"❌ Task failed: {task.task_id} - {str(e)}", exc_info=True)
            task.status = "failed"
            task.result = AgentResult(
                task_id=task.task_id,
                success=False,
                result=None,
                reasoning_chain=[],
                actions_taken=[],
                total_iterations=0,
                execution_time_seconds=0,
                error=str(e),
            )
        
        finally:
            # Move to completed
            self.active_tasks.pop(task.task_id, None)
            self.completed_tasks.append(task)
            
            # Process next task if available
            if self.task_queue and len(self.active_tasks) < self.max_concurrent_agents:
                asyncio.create_task(self._process_next_task())
    
    def _select_agent(self, task: Task) -> BaseAgent:
        """
        Select appropriate agent for task
        
        Uses task type and complexity to choose agent
        """
        # Map task type to agent
        agent_mapping = {
            TaskType.PR_REVIEW: "pr_review",
            TaskType.TEST_GENERATION: "test_generation",
            TaskType.SECURITY_SCAN: "security",
            # Add more mappings
        }
        
        agent_name = agent_mapping.get(task.task_type)
        
        if not agent_name or agent_name not in self.agents:
            raise ValueError(f"No agent available for task type: {task.task_type}")
        
        return self.agents[agent_name]
    
    async def _execute_with_agent(self, agent: BaseAgent, task: Task) -> AgentResult:
        """Execute task with selected agent"""
        # For PR Review Agent
        if isinstance(agent, PRReviewAgent):
            params = task.parameters
            result = await agent.review_pr(
                repo_owner=params["repo_owner"],
                repo_name=params["repo_name"],
                pr_number=params["pr_number"],
                auto_approve=params.get("auto_approve", False),
            )
            return result
        
        # Add handlers for other agent types
        else:
            raise NotImplementedError(f"Execution not implemented for {type(agent)}")
    
    async def _load_task_context(self, task: Task) -> Dict[str, Any]:
        """
        Load relevant context from memory for task
        
        Uses semantic search to find similar past tasks
        """
        # Query memory for similar tasks
        similar_tasks = await self.memory.search_similar_tasks(
            task_type=task.task_type.value,
            parameters=task.parameters,
            limit=5,
        )
        
        # Extract learnings
        learnings = []
        for similar_task in similar_tasks:
            if similar_task.get("success"):
                learnings.append({
                    "task_id": similar_task["task_id"],
                    "actions_taken": similar_task.get("actions_taken", []),
                    "outcome": "success",
                })
        
        return {
            "similar_tasks_count": len(similar_tasks),
            "past_learnings": learnings,
        }
    
    async def _save_task_result(self, task: Task, result: AgentResult):
        """
        Save task result to memory for future learning
        """
        await self.memory.store_task(
            task_id=task.task_id,
            task_type=task.task_type.value,
            parameters=task.parameters,
            result=result.result,
            success=result.success,
            reasoning_chain=result.reasoning_chain,
            actions_taken=result.actions_taken,
        )
    
    def _get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        # Check active tasks
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]
        
        # Check completed tasks
        for task in self.completed_tasks:
            if task.task_id == task_id:
                return task
        
        # Check queue
        for task in self.task_queue:
            if task.task_id == task_id:
                return task
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        return {
            "registered_agents": list(self.agents.keys()),
            "queue_length": len(self.task_queue),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "max_concurrent": self.max_concurrent_agents,
        }
    
    async def handle_webhook(self, event_type: str, payload: Dict[str, Any]):
        """
        Handle GitHub webhook events
        
        Automatically triggers appropriate agents based on events
        """
        self.logger.info(f"📥 Webhook received: {event_type}")
        
        if event_type == "pull_request":
            action = payload.get("action")
            
            # Auto-review new PRs
            if action in ["opened", "synchronize", "reopened"]:
                pr = payload["pull_request"]
                
                await self.submit_task(
                    task_type=TaskType.PR_REVIEW,
                    parameters={
                        "repo_owner": payload["repository"]["owner"]["login"],
                        "repo_name": payload["repository"]["name"],
                        "pr_number": pr["number"],
                        "auto_approve": False,  # Manual approval for safety
                    },
                    priority=7,  # High priority
                )
        
        elif event_type == "workflow_run":
            # Handle CI/CD events
            if payload.get("conclusion") == "failure":
                # Auto-diagnose failures
                self.logger.info("🔧 CI failure detected, queuing diagnosis task")
                # Submit CI fix task
        
        # Add more webhook handlers as needed
    
    async def shutdown(self):
        """Graceful shutdown - wait for active tasks to complete"""
        self.logger.info("🛑 Shutting down orchestrator...")
        
        # Wait for active tasks
        while self.active_tasks:
            self.logger.info(f"Waiting for {len(self.active_tasks)} active tasks...")
            await asyncio.sleep(2)
        
        self.logger.info("✓ All tasks completed, shutdown complete")
