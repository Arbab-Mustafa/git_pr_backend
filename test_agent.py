"""
Quick Start Example - Test the AI Agent System
Run this to see the agent in action
"""

import asyncio
import os
from dotenv import load_dotenv
from groq import Groq

# Import agent system
from app.agents import AgentOrchestrator, PRReviewAgent, TaskType

load_dotenv()


async def test_pr_review_agent():
    """
    Test 1: Direct PR Review Agent
    
    This demonstrates the agent autonomously reviewing a PR
    """
    print("=" * 80)
    print("TEST 1: Direct PR Review Agent")
    print("=" * 80)
    
    # Initialize
    llm = Groq(api_key=os.getenv("GROQ_API_KEY"))
    github_token = os.getenv("GITHUB_TOKEN")
    
    if not github_token or github_token == "your_github_token_here":
        print("❌ GITHUB_TOKEN not configured in .env")
        print("   Get a token from: https://github.com/settings/tokens")
        return
    
    # Create agent
    agent = PRReviewAgent(
        llm_client=llm,
        github_token=github_token,
    )
    
    print("\n🤖 Agent initialized")
    print(f"   Tools available: {len(agent.tools)}")
    print(f"   Max iterations: {agent.max_iterations}")
    
    # Test with a real PR (use a small one for testing)
    print("\n📝 Testing on sample PR...")
    print("   Repo: octocat/Hello-World (GitHub's test repo)")
    print("   PR: #1 (if it exists)")
    print()
    
    # Note: This will fail if PR doesn't exist, which is fine for demo
    try:
        result = await agent.review_pr(
            repo_owner="octocat",
            repo_name="Hello-World",
            pr_number=1,
            auto_approve=False,
        )
        
        print("\n" + "=" * 80)
        print("✅ REVIEW COMPLETED")
        print("=" * 80)
        print(f"Success: {result.success}")
        print(f"Iterations: {result.total_iterations}")
        print(f"Actions taken: {len(result.actions_taken)}")
        print(f"Execution time: {result.execution_time_seconds:.2f}s")
        print()
        
        print("Reasoning chain:")
        for i, thought in enumerate(result.reasoning_chain, 1):
            print(f"  {i}. {thought[:100]}...")
        print()
        
        print("Actions executed:")
        for i, action in enumerate(result.actions_taken, 1):
            print(f"  {i}. {action['tool']}({', '.join(action['parameters'].keys())})")
        print()
        
        if result.result:
            print("Results:")
            for key, value in result.result.items():
                print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"\n⚠️ Expected error (no PR exists in test repo): {str(e)}")
        print("   This is normal! Use your own repo/PR to test.")


async def test_orchestrator():
    """
    Test 2: Agent Orchestrator
    
    This demonstrates the orchestration system with task queue
    """
    print("\n\n" + "=" * 80)
    print("TEST 2: Agent Orchestrator")
    print("=" * 80)
    
    llm = Groq(api_key=os.getenv("GROQ_API_KEY"))
    github_token = os.getenv("GITHUB_TOKEN")
    
    # Create orchestrator
    orchestrator = AgentOrchestrator(
        llm_client=llm,
        github_token=github_token,
        max_concurrent_agents=3,
    )
    
    print("\n🎭 Orchestrator initialized")
    status = orchestrator.get_status()
    print(f"   Registered agents: {status['registered_agents']}")
    print(f"   Max concurrent: {status['max_concurrent']}")
    
    # Submit tasks
    print("\n📋 Submitting tasks...")
    
    task_ids = []
    
    # Task 1: Review a PR
    task_id_1 = await orchestrator.submit_task(
        task_type=TaskType.PR_REVIEW,
        parameters={
            "repo_owner": "octocat",
            "repo_name": "Hello-World",
            "pr_number": 1,
            "auto_approve": False,
        },
        priority=8,
    )
    task_ids.append(task_id_1)
    print(f"   ✓ Task 1 submitted: {task_id_1}")
    
    # Wait a bit for processing
    print("\n⏳ Processing tasks...")
    await asyncio.sleep(2)
    
    # Check status
    print("\n📊 Orchestrator Status:")
    status = orchestrator.get_status()
    print(f"   Queue length: {status['queue_length']}")
    print(f"   Active tasks: {status['active_tasks']}")
    print(f"   Completed: {status['completed_tasks']}")
    
    # Memory stats
    memory_stats = orchestrator.memory.get_stats()
    print(f"\n🧠 Memory Stats:")
    print(f"   Working memory entries: {memory_stats['working_memory_size']}")
    print(f"   Semantic patterns: {memory_stats['semantic_patterns']}")


async def test_memory_system():
    """
    Test 3: Memory System
    
    This demonstrates the three-tier memory
    """
    print("\n\n" + "=" * 80)
    print("TEST 3: Memory System")
    print("=" * 80)
    
    from app.agents.memory import AgentMemory
    
    memory = AgentMemory()
    
    print("\n🧠 Testing memory layers...")
    
    # 1. Working Memory
    print("\n1️⃣ Working Memory (short-term)")
    await memory.working.store("test_key", {"data": "test_value"}, ttl=60)
    retrieved = await memory.working.retrieve("test_key")
    print(f"   Stored and retrieved: {retrieved}")
    
    # 2. Episodic Memory
    print("\n2️⃣ Episodic Memory (task history)")
    await memory.episodic.store_episode(
        task_id="test_task_123",
        task_type="pr_review",
        parameters={"repo": "test/repo", "pr": 1},
        result={"success": True},
        success=True,
        reasoning_chain=["Step 1", "Step 2"],
        actions_taken=[{"tool": "analyze", "params": {}}],
    )
    print("   ✓ Episode stored")
    
    episodes = await memory.episodic.retrieve_episodes(
        task_type="pr_review",
        limit=5,
    )
    print(f"   Retrieved {len(episodes)} episodes")
    
    # 3. Semantic Memory
    print("\n3️⃣ Semantic Memory (learned patterns)")
    await memory.semantic.store_pattern(
        pattern_type="pr_review_workflow",
        pattern="fetch_pr -> analyze_security -> post_comments -> submit_review",
        description="Successful PR review pattern",
        examples=["PR #123", "PR #456"],
        metadata={"success_rate": 0.95},
    )
    print("   ✓ Pattern stored")
    
    patterns = await memory.semantic.search_patterns(
        query="pr_review",
        limit=5,
    )
    print(f"   Found {len(patterns)} patterns")
    if patterns:
        print(f"   Example: {patterns[0]['pattern'][:50]}...")


async def demo_full_workflow():
    """
    Test 4: Complete Workflow Demo
    
    Shows the full agent lifecycle
    """
    print("\n\n" + "=" * 80)
    print("TEST 4: Complete Workflow Demo")
    print("=" * 80)
    
    print("""
This demonstrates the complete agent workflow:

1. 🎯 GOAL: Review PR #1234 in your-repo
2. 🤔 THINK: Agent reasons about what to do
3. 🔧 ACT: Agent executes actions via tools
4. 👀 OBSERVE: Agent processes results
5. 💭 REFLECT: Agent evaluates progress
6. 🔁 REPEAT: Until goal achieved (up to 15 iterations)
7. 🧠 LEARN: Store patterns in memory
8. 📝 RESULT: Complete review with reasoning trace

Example agent reasoning:

Iteration 1:
├─ THINK: "I need to fetch the PR details first"
├─ ACT: get_pr_details(pr_number=1234)
├─ OBSERVE: "Got PR: 'Add new feature', 50 files changed"
└─ REFLECT: "Not done, need to analyze security"

Iteration 2:
├─ THINK: "Let me check for security issues"
├─ ACT: check_security_issues(files=[...])
├─ OBSERVE: "Found 2 SQL injection risks"
└─ REFLECT: "Critical issues, need to comment"

Iteration 3:
├─ THINK: "Post inline comments on vulnerable lines"
├─ ACT: post_inline_comment(line=45, body="SQL injection risk")
├─ OBSERVE: "Comment posted successfully"
└─ REFLECT: "Still need to check test coverage"

... (continues until goal achieved or max iterations)

Final Result:
✅ Review completed
✅ 2 security comments posted
✅ Requested changes due to issues
✅ Learned pattern for future reviews
""")


async def main():
    """Run all tests"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║        🤖 AI AGENT SYSTEM - QUICK START DEMO 🤖              ║
║                                                               ║
║  This demonstrates the production-grade autonomous agent      ║
║  system that can review PRs, take actions, and learn.        ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""")
    
    # Check configuration
    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") == "your_groq_api_key_here":
        print("❌ ERROR: GROQ_API_KEY not configured")
        print("\n📝 Setup instructions:")
        print("   1. Create .env file in backend/ directory")
        print("   2. Add: GROQ_API_KEY=your_key_here")
        print("   3. Add: GITHUB_TOKEN=your_token_here")
        print("\n   Get Groq API key: https://console.groq.com")
        print("   Get GitHub token: https://github.com/settings/tokens")
        return
    
    try:
        # Run tests
        await test_pr_review_agent()
        await test_orchestrator()
        await test_memory_system()
        await demo_full_workflow()
        
        print("\n\n" + "=" * 80)
        print("🎉 DEMO COMPLETE!")
        print("=" * 80)
        print("""
Next steps:
1. Configure with your own GitHub repo/PR
2. Review IMPLEMENTATION_GUIDE.md for detailed usage
3. See AGENT_ARCHITECTURE.md for system design
4. Deploy with docker-compose.yml for production

Questions? Check the documentation or create an issue.
""")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("\nThis error is expected if testing without proper configuration.")
        print("Configure .env with real values and try again.")


if __name__ == "__main__":
    asyncio.run(main())
