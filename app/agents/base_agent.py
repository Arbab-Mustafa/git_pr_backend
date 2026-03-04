"""
Base Agent - Production-grade autonomous agent implementation
Implements ReAct (Reasoning + Acting) pattern with multi-step planning
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from groq import Groq

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentThought:
    """Single reasoning step"""
    content: str
    step_number: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentAction:
    """Action to be executed"""
    tool: str
    parameters: Dict[str, Any]
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentObservation:
    """Result of an action"""
    action: AgentAction
    result: Any
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentState:
    """
    Tracks agent's current state during execution
    This is the "working memory" of the agent
    """
    task_id: str
    goal: str
    status: AgentStatus = AgentStatus.IDLE
    
    # Reasoning chain
    thoughts: List[AgentThought] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    observations: List[AgentObservation] = field(default_factory=list)
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    iteration: int = 0
    
    # Metadata
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    def add_thought(self, content: str) -> None:
        """Add reasoning step"""
        self.thoughts.append(
            AgentThought(content=content, step_number=len(self.thoughts) + 1)
        )
    
    def add_action(self, tool: str, parameters: Dict[str, Any], reasoning: str) -> AgentAction:
        """Record planned action"""
        action = AgentAction(tool=tool, parameters=parameters, reasoning=reasoning)
        self.actions.append(action)
        return action
    
    def add_observation(
        self, action: AgentAction, result: Any, success: bool, error: Optional[str] = None
    ) -> None:
        """Record action result"""
        self.observations.append(
            AgentObservation(action=action, result=result, success=success, error=error)
        )
    
    def get_last_observation(self) -> Optional[AgentObservation]:
        """Get most recent observation"""
        return self.observations[-1] if self.observations else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for storage/transmission"""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "iteration": self.iteration,
            "num_thoughts": len(self.thoughts),
            "num_actions": len(self.actions),
            "context": self.context,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


@dataclass
class AgentResult:
    """Final result from agent execution"""
    task_id: str
    success: bool
    result: Any
    reasoning_chain: List[str]
    actions_taken: List[Dict[str, Any]]
    total_iterations: int
    execution_time_seconds: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Base class for all autonomous agents
    
    Implements the ReAct (Reasoning + Acting) pattern:
    1. THINK - Reason about current state
    2. ACT - Take action based on reasoning
    3. OBSERVE - Process action results
    4. REFLECT - Evaluate progress toward goal
    5. REPEAT until goal achieved or max iterations
    
    Production features:
    - Multi-step reasoning
    - Error recovery
    - State persistence
    - Timeout handling
    - Cost tracking
    """
    
    def __init__(
        self,
        name: str,
        llm_client: Groq,
        tools: Dict[str, callable],
        max_iterations: int = 10,
        timeout_seconds: int = 300,
    ):
        self.name = name
        self.llm = llm_client
        self.tools = tools
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        
        self.logger = logging.getLogger(f"agent.{name}")
        self.logger.info(f"🤖 Initialized agent: {name}")
    
    async def execute(self, goal: str, context: Dict[str, Any]) -> AgentResult:
        """
        Main execution loop - ReAct pattern implementation
        
        Args:
            goal: What the agent should accomplish
            context: Initial context/input data
            
        Returns:
            AgentResult with outcome and execution trace
        """
        # Initialize state
        state = AgentState(
            task_id=f"{self.name}_{int(time.time())}",
            goal=goal,
            context=context,
        )
        
        self.logger.info(f"🎯 Starting task: {goal}")
        start_time = time.time()
        
        try:
            # ReAct loop
            for iteration in range(1, self.max_iterations + 1):
                state.iteration = iteration
                self.logger.info(f"🔄 Iteration {iteration}/{self.max_iterations}")
                
                # Check timeout
                if time.time() - start_time > self.timeout_seconds:
                    raise TimeoutError(f"Agent exceeded timeout of {self.timeout_seconds}s")
                
                # 1. THINK - Reason about what to do next
                state.status = AgentStatus.THINKING
                thought = await self._reason(state)
                state.add_thought(thought)
                self.logger.debug(f"💭 Thought: {thought[:100]}...")
                
                # 2. ACT - Plan and execute action
                state.status = AgentStatus.ACTING
                action = await self._plan_action(thought, state)
                
                if action is None:
                    # No action needed - goal achieved
                    self.logger.info("✅ Goal achieved, no further action needed")
                    break
                
                # Check for action repetition (anti-loop mechanism)
                if self._is_action_repeated(action, state):
                    self.logger.warning(f"⚠️ Action {action.tool} already executed recently - forcing replan")
                    await self._replan(state)
                    continue
                
                self.logger.info(f"🔧 Action: {action.tool}({list(action.parameters.keys())})")
                observation = await self._execute_action(action, state)
                
                # 3. OBSERVE - Process results
                state.status = AgentStatus.OBSERVING
                state.add_observation(
                    action=action,
                    result=observation.get("result"),
                    success=observation.get("success", True),
                    error=observation.get("error"),
                )
                
                # 4. REFLECT - Check if goal achieved
                state.status = AgentStatus.REFLECTING
                if await self._is_goal_achieved(state):
                    self.logger.info("✅ Goal achieved")
                    break
                
                # Check if replanning needed
                if await self._needs_replanning(state):
                    self.logger.info("🔄 Replanning strategy...")
                    await self._replan(state)
            
            # Success
            state.status = AgentStatus.COMPLETED
            state.end_time = datetime.utcnow()
            
            result = await self._generate_result(state)
            execution_time = time.time() - start_time
            
            self.logger.info(
                f"✅ Task completed in {execution_time:.2f}s "
                f"({state.iteration} iterations, {len(state.actions)} actions)"
            )
            
            return AgentResult(
                task_id=state.task_id,
                success=True,
                result=result,
                reasoning_chain=[t.content for t in state.thoughts],
                actions_taken=[
                    {"tool": a.tool, "parameters": a.parameters, "reasoning": a.reasoning}
                    for a in state.actions
                ],
                total_iterations=state.iteration,
                execution_time_seconds=execution_time,
            )
            
        except Exception as e:
            # Failure handling
            state.status = AgentStatus.FAILED
            state.end_time = datetime.utcnow()
            execution_time = time.time() - start_time
            
            # Check for rate limit errors
            error_msg = str(e)
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                self.logger.warning(f"⏱️ Rate limit hit: {error_msg}")
                # Extract wait time if available
                import re
                wait_match = re.search(r'(\d+)m(\d+)', error_msg)
                if wait_match:
                    minutes = wait_match.group(1)
                    self.logger.info(f"💡 Wait {minutes} minutes or use a different API key")
            else:
                self.logger.error(f"❌ Task failed: {error_msg}", exc_info=True)
            
            return AgentResult(
                task_id=state.task_id,
                success=False,
                result=None,
                reasoning_chain=[t.content for t in state.thoughts],
                actions_taken=[
                    {"tool": a.tool, "parameters": a.parameters}
                    for a in state.actions
                ],
                total_iterations=state.iteration,
                execution_time_seconds=execution_time,
                error=str(e),
            )
    
    async def _reason(self, state: AgentState) -> str:
        """
        THINK step - Reason about current state and what to do next
        
        This is where the LLM analyzes the situation and decides on next steps
        """
        # Build reasoning prompt
        prompt = self._build_reasoning_prompt(state)
        
        # Call LLM for reasoning
        response = self.llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": self._get_system_prompt(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,  # Lower temperature for more focused reasoning
            max_tokens=1000,
        )
        
        thought = response.choices[0].message.content.strip()
        return thought
    
    async def _plan_action(self, thought: str, state: AgentState) -> Optional[AgentAction]:
        """
        ACT step - Convert reasoning into concrete action
        
        Returns None if no action needed (goal achieved)
        """
        # Build action planning prompt
        prompt = self._build_action_prompt(thought, state)
        
        # Call LLM to plan action
        response = self.llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an action planner. Convert reasoning into specific tool calls.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.1,  # Very low temperature for precise actions
            max_tokens=500,
        )
        
        action_text = response.choices[0].message.content.strip()
        
        # Parse action (format: TOOL: tool_name | PARAMS: {json} | REASON: reason)
        if "NO_ACTION" in action_text or "GOAL_ACHIEVED" in action_text:
            return None
        
        action = self._parse_action(action_text)
        state.add_action(
            tool=action["tool"],
            parameters=action["parameters"],
            reasoning=action["reasoning"],
        )
        
        return state.actions[-1]
    
    async def _execute_action(self, action: AgentAction, state: AgentState) -> Dict[str, Any]:
        """
        Execute tool call and return observation
        """
        tool = self.tools.get(action.tool)
        
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{action.tool}' not found. Available tools: {', '.join(self.tools.keys())}",
                "result": None,
            }
        
        try:
            # Merge context into parameters if needed
            # This auto-injects repo_owner, repo_name, pr_number for GitHub tools
            params = action.parameters.copy()
            
            # Inject context values if not already present
            for key in ['repo_owner', 'repo_name', 'pr_number']:
                if key not in params and key in state.context:
                    params[key] = state.context[key]
            
            # Execute tool
            result = await tool(**params)
            
            # Extract and store reusable data in working memory
            self._extract_data_to_context(action.tool, result, state)
            
            return {
                "success": True,
                "result": result,
                "error": None,
            }
            
        except TypeError as e:
            # Parameter mismatch - provide helpful error
            error_msg = f"Parameter error for {action.tool}: {str(e)}. "
            error_msg += f"Provided params: {list(params.keys())}. "
            error_msg += f"Check the tool signature and try again with correct parameters."
            self.logger.error(f"Tool execution failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "result": None,
            }
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.logger.error(f"Tool execution failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "result": None,
            }
    
    def _extract_data_to_context(self, tool_name: str, result: Any, state: AgentState) -> None:
        """
        Extract critical data from tool results and store in working memory
        This is the KEY to preventing infinite loops - extracted data is reused
        """
        if result is None or not isinstance(result, dict):
            return
        
        try:
            # Extract from get_pr_details - MOST CRITICAL
            if tool_name == "get_pr_details":
                # Extract commit SHAs (needed for post_inline_comment)
                if 'head' in result and 'sha' in result['head']:
                    state.context['commit_sha'] = result['head']['sha']
                    state.context['commit_id'] = result['head']['sha']  # Alias
                    self.logger.info(f"📌 Extracted commit_sha: {result['head']['sha'][:8]}")
                
                if 'base' in result and 'sha' in result['base']:
                    state.context['base_sha'] = result['base']['sha']
                
                # Extract file list (needed for analysis)
                if 'files' in result and isinstance(result['files'], list):
                    files = [f.get('filename') for f in result['files'] if 'filename' in f]
                    state.context['pr_files'] = files
                    state.context['file_count'] = len(files)
                    self.logger.info(f"📌 Extracted {len(files)} files from PR")
                    
                    # Extract file metadata
                    for file_data in result['files']:
                        filename = file_data.get('filename')
                        if filename:
                            state.context[f'file_meta_{filename}'] = {
                                'additions': file_data.get('additions', 0),
                                'deletions': file_data.get('deletions', 0),
                                'changes': file_data.get('changes', 0),
                                'status': file_data.get('status', 'modified'),
                            }
                
                # Mark as fetched
                state.context['pr_details_fetched'] = True
            
            # Extract from get_pr_files
            elif tool_name == "get_pr_files":
                if isinstance(result, list):
                    files = []
                    for file_data in result:
                        if 'filename' in file_data:
                            filename = file_data['filename']
                            files.append(filename)
                            
                            # Store patches for inline commenting
                            if 'patch' in file_data:
                                state.context[f'patch_{filename}'] = file_data['patch']
                    
                    state.context['pr_files'] = files
                    state.context['pr_files_fetched'] = True
                    self.logger.info(f"📌 Extracted {len(files)} file patches")
            
            # Extract from get_file_content
            elif tool_name == "get_file_content":
                # Result is the file content string
                # Store it with a key based on parameters if we can identify the file
                pass  # Content is already in result, accessible via observations
            
            # Track analysis completion
            elif tool_name == "analyze_code_quality":
                if isinstance(result, dict):
                    state.context['code_quality_analyzed'] = True
                    if 'issues' in result:
                        state.context['quality_issues_count'] = len(result['issues'])
            
            elif tool_name == "check_security_issues":
                if isinstance(result, dict):
                    state.context['security_checked'] = True
                    if 'issues' in result:
                        state.context['security_issues_count'] = len(result['issues'])
            
            # Track write operations
            elif tool_name == "post_review_comment":
                state.context.setdefault('review_comments_posted', 0)
                state.context['review_comments_posted'] += 1
                self.logger.info(f"📌 Review comment posted (total: {state.context['review_comments_posted']})")
            
            elif tool_name == "post_inline_comment":
                state.context.setdefault('inline_comments_posted', 0)
                state.context['inline_comments_posted'] += 1
                self.logger.info(f"📌 Inline comment posted (total: {state.context['inline_comments_posted']})")
            
            elif tool_name in ["submit_review", "approve_pr", "request_changes"]:
                state.context['review_submitted'] = True
                state.context['review_action'] = tool_name
                self.logger.info(f"📌 Review submitted: {tool_name}")
        
        except Exception as e:
            self.logger.warning(f"Data extraction failed for {tool_name}: {e}")
            # Don't fail the action, just log the warning
    
    async def _is_goal_achieved(self, state: AgentState) -> bool:
        """
        REFLECT step - Check if goal is achieved
        Uses working memory to track progress
        """
        # Get last observation
        last_obs = state.get_last_observation()
        if not last_obs:
            return False
        
        # FAST PATH: Check working memory for completion markers
        # If review submitted, goal is achieved
        if state.context.get('review_submitted'):
            self.logger.info("✅ Review submitted - goal achieved!")
            return True
        
        # If many comments posted and PR analyzed, goal is achieved
        comments_posted = (
            state.context.get('review_comments_posted', 0) + 
            state.context.get('inline_comments_posted', 0)
        )
        
        if comments_posted >= 3 and state.context.get('code_quality_analyzed'):
            self.logger.info(f"✅ {comments_posted} comments posted and analysis done - goal achieved!")
            return True
        
        # Quick checks for obvious completion
        # If we've taken 10+ actions successfully, likely done
        if len(state.actions) >= 10:
            successful_actions = [obs for obs in state.observations if obs.success]
            if len(successful_actions) >= 8:
                self.logger.info("📊 10+ actions completed successfully - goal likely achieved")
                return True
        
        # SLOW PATH: Ask LLM if goal achieved with full context
        recent_actions = "\n".join([
            f"{i+1}. {obs.action.tool} → {'✓' if obs.success else '✗'}"
            for i, obs in enumerate(state.observations[-5:])
        ])
        
        # Build progress summary
        progress_items = []
        if state.context.get('pr_details_fetched'):
            progress_items.append("✓ PR details fetched")
        if state.context.get('code_quality_analyzed'):
            progress_items.append("✓ Code quality analyzed")
        if state.context.get('security_checked'):
            progress_items.append("✓ Security checked")
        if comments_posted > 0:
            progress_items.append(f"✓ {comments_posted} comments posted")
        if state.context.get('review_submitted'):
            progress_items.append("✓ Review submitted")
        
        progress_summary = "\n".join(progress_items) if progress_items else "No progress yet"
        
        prompt = f"""
Goal: {state.goal}

Progress:
{progress_summary}

Recent actions:
{recent_actions}

Total actions: {len(state.actions)}
Successful: {sum(1 for o in state.observations if o.success)}

Based on the goal and progress, has the goal been FULLY achieved?

Respond with ONLY: YES or NO
"""
        
        response = self.llm.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    
    def _is_action_repeated(self, action: AgentAction, state: AgentState) -> bool:
        """
        Check if this action was recently executed (anti-loop mechanism)
        IMPROVED: Allow retries if data extraction failed
        """
        # Check last 3 actions
        recent_actions = state.actions[-3:] if len(state.actions) >= 3 else state.actions
        
        for past_action in recent_actions:
            # Same tool with same or similar parameters = repetition
            if past_action.tool == action.tool:
                # SPECIAL CASE: Allow get_pr_details retry if data not in context
                if action.tool == "get_pr_details":
                    if not state.context.get('pr_details_fetched') or not state.context.get('commit_sha'):
                        # Data extraction failed, allow retry
                        self.logger.info(f"🔄 Allowing {action.tool} retry - data not in context")
                        return False
                    else:
                        # Data successfully extracted, block duplicate
                        return True
                
                # SPECIAL CASE: Allow get_pr_files retry if not fetched
                elif action.tool == "get_pr_files":
                    if not state.context.get('pr_files_fetched'):
                        return False
                    return True
                
                # For read operations (get_*), check if parameters are identical
                elif action.tool.startswith('get_'):
                    if past_action.parameters == action.parameters:
                        return True
                
                # For write operations, check exact parameter match
                elif action.tool in ['post_inline_comment', 'post_review_comment']:
                    # These can be called multiple times with different params
                    if past_action.parameters == action.parameters:
                        return True  # Exact duplicate
                    return False  # Different params, allow
                
                # For final actions (submit_review, approve, request_changes)
                elif action.tool in ['submit_review', 'approve_pr', 'request_changes']:
                    # These should only be done once
                    if state.context.get('review_submitted'):
                        return True
                    return False
                
                # For other operations, any repetition within 3 actions is suspicious
                else:
                    return True
        
        return False
    
    async def _needs_replanning(self, state: AgentState) -> bool:
        """Check if strategy needs adjustment"""
        # Check for repeated failures
        recent_failures = [
            obs for obs in state.observations[-3:]
            if not obs.success
        ]
        
        return len(recent_failures) >= 2
    
    async def _replan(self, state: AgentState) -> None:
        """Adjust strategy based on failures"""
        self.logger.info("🔄 Replanning strategy...")
        
        # Analyze recent failures
        recent_failures = [obs for obs in state.observations[-3:] if not obs.success]
        
        if not recent_failures:
            return
        
        # Build replanning prompt
        failure_summary = "\n".join([
            f"- {obs.action.tool}: {obs.error}"
            for obs in recent_failures
        ])
        
        replan_prompt = f"""
You have encountered errors. Analyze and adjust your strategy.

GOAL: {state.goal}

RECENT FAILURES:
{failure_summary}

GUIDANCE:
- If tool is not found, check available tools list
- If parameter error, review tool signatures carefully
- If GitHub API error, the PR/repo might not exist - verify details first
- Consider alternative approaches to achieve the goal

Provide a brief strategy adjustment (1-2 sentences) on how to proceed differently.
"""
        
        try:
            response = self.llm.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a strategic planner helping an agent recover from errors."},
                    {"role": "user", "content": replan_prompt}
                ],
                temperature=0.3,
                max_tokens=200,
            )
            
            strategy = response.choices[0].message.content.strip()
            state.add_thought(f"REPLANNING: {strategy}")
            self.logger.info(f"📝 New strategy: {strategy}")
            
        except Exception as e:
            self.logger.error(f"Replanning failed: {e}")
            state.add_thought("REPLANNING: Continue with current approach")
    
    async def _generate_result(self, state: AgentState) -> Any:
        """Generate final result from agent state"""
        # Default implementation - subclasses should override
        return {
            "status": "completed",
            "actions_taken": len(state.actions),
            "iterations": state.iteration,
        }
    
    def _build_reasoning_prompt(self, state: AgentState) -> str:
        """Build prompt for reasoning step"""
        # Get previous context
        previous_thoughts = "\n".join([
            f"{i+1}. {t.content[:150]}..."
            for i, t in enumerate(state.thoughts[-2:])  # Last 2 thoughts only
        ])
        
        previous_observations = "\n".join([
            f"{i+1}. {obs.action.tool} → {'✓ Success' if obs.success else f'✗ ERROR: {obs.error}'}"
            for i, obs in enumerate(state.observations[-5:])  # Last 5 observations
        ])
        
        # Build DETAILED data summary from working memory
        data_items = []
        
        # PR Details
        if state.context.get('pr_details_fetched'):
            data_items.append("✓ PR Details Fetched:")
            if state.context.get('commit_sha'):
                data_items.append(f"  - Commit SHA: {state.context['commit_sha'][:8]}... (use for inline comments)")
            if state.context.get('pr_files'):
                files = state.context['pr_files']
                data_items.append(f"  - Files changed: {len(files)}")
                if len(files) <= 5:
                    data_items.append(f"  - File names: {', '.join(files)}")
                else:
                    data_items.append(f"  - File names: {', '.join(files[:3])} ... and {len(files)-3} more")
        
        # Analysis Results
        if state.context.get('code_quality_analyzed'):
            issues_count = state.context.get('quality_issues_count', 0)
            data_items.append(f"✓ Code Quality Analyzed: {issues_count} issues found")
        
        if state.context.get('security_checked'):
            issues_count = state.context.get('security_issues_count', 0)
            data_items.append(f"✓ Security Checked: {issues_count} issues found")
        
        # Comments Posted
        if state.context.get('review_comments_posted', 0) > 0:
            data_items.append(f"✓ Review Comments Posted: {state.context['review_comments_posted']}")
        
        if state.context.get('inline_comments_posted', 0) > 0:
            data_items.append(f"✓ Inline Comments Posted: {state.context['inline_comments_posted']}")
        
        # Review Status
        if state.context.get('review_submitted'):
            data_items.append(f"✓ Review Submitted: {state.context.get('review_action', 'unknown')}")
        
        data_summary = "\n".join(data_items) if data_items else "❌ No data in working memory yet - start by fetching PR details"
        
        return f"""
You are analyzing a task to decide what to do next.

GOAL: {state.goal}

BASE CONTEXT: {state.context.get('repo_owner')}/{state.context.get('repo_name')} PR #{state.context.get('pr_number')}

ITERATION: {state.iteration}/{self.max_iterations}

WORKING MEMORY (DATA YOU CAN USE):
{data_summary}

RECENT ACTIONS (last 5):
{previous_observations if previous_observations else "None yet"}

CRITICAL RULES:
1. ⚠️ USE THE WORKING MEMORY DATA - Don't refetch what you already have!
2. If commit_sha is in memory, use it directly for post_inline_comment
3. If files are in memory, analyze them - don't call get_pr_details again
4. Only fetch data once, then move to next step
5. Progress through workflow: fetch → analyze → comment → submit
6. If you've tried the same action 2+ times, try something different

What specific action should you take next? Be concrete and brief.
"""
    
    def _build_action_prompt(self, thought: str, state: AgentState) -> str:
        """Build prompt for action planning"""
        import inspect
        
        # Build tool descriptions with parameter hints
        tool_descriptions = []
        for name, tool in self.tools.items():
            doc = tool.__doc__ or 'No description'
            # Get function signature
            try:
                sig = inspect.signature(tool)
                params = list(sig.parameters.keys())
                # Remove 'self' if present
                params = [p for p in params if p != 'self']
                param_str = ", ".join(params)
                tool_descriptions.append(f"- {name}({param_str}): {doc.strip()}")
            except:
                tool_descriptions.append(f"- {name}: {doc.strip()}")
        
        available_tools = "\n".join(tool_descriptions)
        
        # Extract context info
        context_info = ""
        if state.context:
            context_keys = ", ".join([f"{k}={v}" for k, v in state.context.items()])
            context_info = f"\n\nCONTEXT (available for all tools):\n{context_keys}\n"
        
        return f"""
Based on this reasoning: {thought}

Convert it into a specific tool call.

AVAILABLE TOOLS:
{available_tools}
{context_info}

IMPORTANT: 
- For GitHub tools, repo_owner, repo_name, and pr_number are automatically provided from context
- You do NOT need to include them in PARAMS
- Only specify the unique parameters for each tool call

Format your response as:
TOOL: tool_name
PARAMS: {{"param1": "value1", "param2": "value2"}}
REASON: Why this action

Or respond with: GOAL_ACHIEVED if no action needed.
"""
    
    def _parse_action(self, action_text: str) -> Dict[str, Any]:
        """Parse action from LLM response"""
        import json
        import re
        
        # Extract tool name
        tool_match = re.search(r'TOOL:\s*(\w+)', action_text)
        tool = tool_match.group(1) if tool_match else "unknown"
        
        # Extract parameters
        params_match = re.search(r'PARAMS:\s*(\{[^}]+\})', action_text)
        params = {}
        if params_match:
            try:
                params = json.loads(params_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Extract reasoning
        reason_match = re.search(r'REASON:\s*(.+)', action_text, re.DOTALL)
        reasoning = reason_match.group(1).strip() if reason_match else ""
        
        return {
            "tool": tool,
            "parameters": params,
            "reasoning": reasoning,
        }
    
    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Get agent-specific system prompt"""
        pass
