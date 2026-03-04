"""
Agent Memory System - Production implementation
Three-tier memory: Working, Episodic, Semantic
"""

import logging
import json
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Single memory entry"""
    id: str
    memory_type: str  # working, episodic, semantic
    content: Dict[str, Any]
    embedding: Optional[List[float]] = None
    timestamp: datetime = None
    ttl: Optional[int] = None  # Time to live in seconds
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}


class WorkingMemory:
    """
    Short-term memory for current task context
    
    - Stores current task state
    - TTL: 1 hour
    - Storage: In-memory dict (Redis in production)
    """
    
    def __init__(self):
        self._memory: Dict[str, MemoryEntry] = {}
        self.logger = logging.getLogger("memory.working")
    
    async def store(
        self,
        key: str,
        content: Dict[str, Any],
        ttl: int = 3600,  # 1 hour default
    ):
        """Store in working memory"""
        entry = MemoryEntry(
            id=key,
            memory_type="working",
            content=content,
            ttl=ttl,
        )
        
        self._memory[key] = entry
        self.logger.debug(f"Stored in working memory: {key}")
    
    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve from working memory"""
        entry = self._memory.get(key)
        
        if not entry:
            return None
        
        # Check TTL
        if entry.ttl:
            age = (datetime.utcnow() - entry.timestamp).total_seconds()
            if age > entry.ttl:
                # Expired
                del self._memory[key]
                return None
        
        return entry.content
    
    async def clear(self, key: Optional[str] = None):
        """Clear working memory"""
        if key:
            self._memory.pop(key, None)
        else:
            self._memory.clear()
    
    def get_size(self) -> int:
        """Get number of entries"""
        return len(self._memory)


class EpisodicMemory:
    """
    Medium-term memory for task history
    
    - Stores completed tasks and their outcomes
    - Retention: 90 days
    - Storage: PostgreSQL (file-based for demo)
    """
    
    def __init__(self, storage_path: str = "./data/episodic_memory.jsonl"):
        self.storage_path = storage_path
        self.logger = logging.getLogger("memory.episodic")
        
        # Ensure storage directory exists
        import os
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
    
    async def store_episode(
        self,
        task_id: str,
        task_type: str,
        parameters: Dict[str, Any],
        result: Any,
        success: bool,
        reasoning_chain: List[str],
        actions_taken: List[Dict[str, Any]],
    ):
        """
        Store completed task as episode
        """
        episode = {
            "task_id": task_id,
            "task_type": task_type,
            "parameters": parameters,
            "result": result,
            "success": success,
            "reasoning_chain": reasoning_chain,
            "actions_taken": actions_taken,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Append to storage
        with open(self.storage_path, "a") as f:
            f.write(json.dumps(episode) + "\n")
        
        self.logger.info(f"Stored episode: {task_id}")
    
    async def retrieve_episodes(
        self,
        task_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve episodes matching criteria
        """
        import os
        if not os.path.exists(self.storage_path):
            return []
        
        episodes = []
        cutoff_time = since or (datetime.utcnow() - timedelta(days=90))
        
        with open(self.storage_path, "r") as f:
            for line in f:
                try:
                    episode = json.loads(line)
                    
                    # Filter by task type
                    if task_type and episode.get("task_type") != task_type:
                        continue
                    
                    # Filter by time
                    episode_time = datetime.fromisoformat(episode["timestamp"])
                    if episode_time < cutoff_time:
                        continue
                    
                    episodes.append(episode)
                    
                    if len(episodes) >= limit:
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        return episodes
    
    async def get_success_rate(self, task_type: str) -> float:
        """Get success rate for task type"""
        episodes = await self.retrieve_episodes(task_type=task_type)
        
        if not episodes:
            return 0.0
        
        successes = sum(1 for ep in episodes if ep.get("success"))
        return successes / len(episodes)


class SemanticMemory:
    """
    Long-term memory for learned patterns and knowledge
    
    - Stores code patterns, best practices, learned insights
    - Retention: Permanent
    - Storage: Vector database (Pinecone/Weaviate in production)
    
    For this demo, we'll use a simple file-based approach
    """
    
    def __init__(self, storage_path: str = "./data/semantic_memory.json"):
        self.storage_path = storage_path
        self.logger = logging.getLogger("memory.semantic")
        self._memory: Dict[str, Dict[str, Any]] = {}
        
        # Load from disk
        self._load()
    
    def _load(self):
        """Load semantic memory from disk"""
        import os
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r") as f:
                self._memory = json.load(f)
            self.logger.info(f"Loaded {len(self._memory)} semantic memories")
    
    def _save(self):
        """Save semantic memory to disk"""
        import os
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        with open(self.storage_path, "w") as f:
            json.dump(self._memory, f, indent=2)
    
    async def store_pattern(
        self,
        pattern_type: str,
        pattern: str,
        description: str,
        examples: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Store learned code pattern or best practice
        """
        pattern_id = hashlib.md5(pattern.encode()).hexdigest()
        
        self._memory[pattern_id] = {
            "id": pattern_id,
            "type": pattern_type,
            "pattern": pattern,
            "description": description,
            "examples": examples,
            "metadata": metadata or {},
            "learned_at": datetime.utcnow().isoformat(),
            "usage_count": 0,
        }
        
        self._save()
        self.logger.info(f"Stored pattern: {pattern_type} - {pattern_id}")
    
    async def search_patterns(
        self,
        query: str,
        pattern_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant patterns
        
        In production, this would use vector similarity search
        For demo, we use simple keyword matching
        """
        results = []
        query_lower = query.lower()
        
        for pattern_id, pattern_data in self._memory.items():
            # Filter by type
            if pattern_type and pattern_data.get("type") != pattern_type:
                continue
            
            # Simple keyword matching
            pattern_text = f"{pattern_data.get('pattern', '')} {pattern_data.get('description', '')}"
            if query_lower in pattern_text.lower():
                results.append(pattern_data)
                
                if len(results) >= limit:
                    break
        
        return results
    
    async def get_all_patterns(self) -> List[Dict[str, Any]]:
        """Get all stored patterns"""
        return list(self._memory.values())
    
    async def increment_usage(self, pattern_id: str):
        """Increment usage count for pattern"""
        if pattern_id in self._memory:
            self._memory[pattern_id]["usage_count"] += 1
            self._save()


class AgentMemory:
    """
    Unified memory interface for agents
    
    Combines three memory tiers:
    1. Working Memory (short-term)
    2. Episodic Memory (medium-term)
    3. Semantic Memory (long-term)
    """
    
    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        
        self.logger = logging.getLogger("memory")
        self.logger.info("🧠 Agent Memory System initialized")
    
    async def store_task(
        self,
        task_id: str,
        task_type: str,
        parameters: Dict[str, Any],
        result: Any,
        success: bool,
        reasoning_chain: List[str],
        actions_taken: List[Dict[str, Any]],
    ):
        """
        Store completed task in episodic memory
        """
        await self.episodic.store_episode(
            task_id=task_id,
            task_type=task_type,
            parameters=parameters,
            result=result,
            success=success,
            reasoning_chain=reasoning_chain,
            actions_taken=actions_taken,
        )
        
        # If task was particularly successful, extract patterns for semantic memory
        if success and len(actions_taken) > 0:
            await self._extract_learnings(task_type, actions_taken, result)
    
    async def search_similar_tasks(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar past tasks
        
        Used to provide context for new tasks
        """
        # Get recent episodes of same type
        episodes = await self.episodic.retrieve_episodes(
            task_type=task_type,
            limit=limit * 2,  # Get more, then filter
        )
        
        # Filter for successful ones
        successful = [ep for ep in episodes if ep.get("success")]
        
        return successful[:limit]
    
    async def _extract_learnings(
        self,
        task_type: str,
        actions: List[Dict[str, Any]],
        result: Any,
    ):
        """
        Extract patterns from successful tasks
        
        This is where the agent "learns" from experience
        """
        # Example: Learn common action sequences
        if len(actions) >= 3:
            action_sequence = " -> ".join([a.get("tool", "") for a in actions[:5]])
            
            await self.semantic.store_pattern(
                pattern_type=f"{task_type}_workflow",
                pattern=action_sequence,
                description=f"Successful workflow for {task_type}",
                examples=[str(result)],
                metadata={"action_count": len(actions)},
            )
    
    async def get_context_for_task(
        self,
        task_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get relevant context from memory for a new task
        
        Combines episodic and semantic memory
        """
        # Get similar past tasks
        similar_tasks = await self.search_similar_tasks(
            task_type=task_type,
            parameters=parameters,
            limit=3,
        )
        
        # Get learned patterns
        patterns = await self.semantic.search_patterns(
            query=task_type,
            pattern_type=f"{task_type}_workflow",
            limit=3,
        )
        
        # Get success rate
        success_rate = await self.episodic.get_success_rate(task_type)
        
        return {
            "similar_tasks": similar_tasks,
            "learned_patterns": patterns,
            "success_rate": success_rate,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            "working_memory_size": self.working.get_size(),
            "semantic_patterns": len(self.semantic._memory),
        }
