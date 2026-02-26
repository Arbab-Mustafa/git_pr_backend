"""Groq AI service for PR analysis"""

import json
import logging
import time
from typing import Dict, Any, Optional
from groq import Groq, GroqError
from app.config import settings
from app.models import PRAnalyzeRequest, PRContext

logger = logging.getLogger(__name__)


class GroqService:
    """Service to interact with Groq AI API"""
    
    def __init__(self):
        """Initialize Groq client"""
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "your_groq_api_key_here":
            raise ValueError(
                "GROQ_API_KEY not configured. "
                "Get your free API key from https://console.groq.com"
            )
        
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL
        logger.info(f"Groq service initialized with model: {self.model}")
    
    def _build_analysis_prompt(self, pr_data: PRAnalyzeRequest) -> str:
        """Build EXPERT-LEVEL prompt for TOP 1% PR analysis"""
        
        # Analyze files with DEEP INSIGHTS
        files_summary = []
        total_additions = 0
        total_deletions = 0
        file_types = {}
        large_changes = []
        
        for i, file in enumerate(pr_data.files[:30], 1):  # Increased to 30
            files_summary.append(
                f"  {i}. {file.filename} ({file.status}): "
                f"+{file.additions}/-{file.deletions}"
            )
            total_additions += file.additions
            total_deletions += file.deletions
            
            # Track patterns for intelligent analysis
            ext = file.filename.split('.')[-1] if '.' in file.filename else 'unknown'
            file_types[ext] = file_types.get(ext, 0) + 1
            
            if file.additions + file.deletions > 500:
                large_changes.append(f"{file.filename} ({file.additions + file.deletions} lines)")
        
        if len(pr_data.files) > 30:
            files_summary.append(f"  ... and {len(pr_data.files) - 30} more files")
        
        # Analyze commits for patterns
        commits_summary = []
        for i, commit in enumerate(pr_data.commits[:15], 1):  # Increased to 15
            commits_summary.append(f"  {i}. {commit.message[:150]}")
        
        if len(pr_data.commits) > 15:
            commits_summary.append(f"  ... and {len(pr_data.commits) - 15} more commits")
        
        # Build INTELLIGENT stats summary
        # Detect if we only have summary data (not individual files)
        has_individual_files = any(not f.filename.startswith('[') and not f.filename.startswith('SUMMARY') and not f.filename.startswith('LIMITATION') and not f.filename.startswith('ℹ️') for f in pr_data.files[:5])
        
        stats_section = f"""
📊 CODE CHANGE STATISTICS:
- Total Files: {len(pr_data.files)} files
- Total Additions: +{total_additions} lines  
- Total Deletions: -{total_deletions} lines
- Net Change Volume: {total_additions + total_deletions} lines modified"""
        
        if has_individual_files:
            file_types_str = ', '.join([f'{k}({v})' for k, v in sorted(file_types.items(), key=lambda x: -x[1])[:5]])
            stats_section += f"\n- File Types: {file_types_str}"
            if large_changes:
                stats_section += f"\n- ⚠️ Large Changes (>500 lines): {', '.join(large_changes[:3])}"
        else:
            stats_section += "\n- ⚠️ DATA LIMITATION: Only summary stats available (user is viewing Conversation tab, not Files tab)"
            stats_section += "\n- NOTE: Individual file names and per-file breakdowns not available - focus analysis on overall change volume and patterns from title/description"
        
        # Build EXPERT-LEVEL prompt
        prompt = f"""🎯 You are a SENIOR STAFF ENGINEER at a top tech company (Google/Meta/Amazon level). You're performing an EXPERT code review that will guide critical engineering decisions. Your analysis must be SPECIFIC, PROFESSIONAL, and ACTIONABLE - absolutely NO generic advice.

═══════════════════════════════════════════════════════════════
📝 PULL REQUEST CONTEXT
═══════════════════════════════════════════════════════════════
Title: {pr_data.title}
Description: {pr_data.description[:1500] if pr_data.description else "No description provided"}
Base Branch: {pr_data.base_branch}
Head Branch: {pr_data.head_branch}

{stats_section}

📂 FILES CHANGED ({len(pr_data.files)} files):
{chr(10).join(files_summary)}

📋 COMMITS ({len(pr_data.commits)} commits):
{chr(10).join(commits_summary) if commits_summary else "No commits information"}

═══════════════════════════════════════════════════════════════
🔍 EXPERT ANALYSIS REQUIREMENTS
═══════════════════════════════════════════════════════════════

✅ MUST BE:
• SPECIFIC to THIS PR (cite actual files when available, or infer from title/description)
• INSIGHTFUL (show architectural thinking, not obvious observations)
• ACTIONABLE (concrete steps, not vague advice like "test thoroughly")
• PROFESSIONAL (technical precision, industry terminology)

❌ NEVER SAY:
• Generic advice ("ensure proper testing", "check for bugs")
• Obvious statements ("files were modified", "code changed")
• Vague warnings ("could have issues", "might cause problems")
• "0 lines" or "change volume is 0" when stats show otherwise
❌ BE SPECIFIC OR DON'T MENTION IT

⚠️ IMPORTANT - DATA CONTEXT:
{f"Individual file names ARE available - cite specific files from the list above." if has_individual_files else "⚠️ ONLY SUMMARY DATA AVAILABLE (Conversation tab view) - You have: total file count, additions/deletions, but NOT individual file names. Infer changes from PR TITLE, DESCRIPTION, and total change volume. Example: If title says 'Fix ESLint rule for refs', discuss ESLint rule changes specifically even without file names."}

Respond with EXPERT JSON analysis:
{{
  "summary": "2-3 sentences citing ACTUAL NUMBERS from 'CODE CHANGE STATISTICS' above ({total_additions}+ additions, {total_deletions}- deletions across {len(pr_data.files)} files). {f'Mention specific files from FILES CHANGED list.' if has_individual_files else 'Since file names unavailable, infer changes from PR title/description.'} Example: '{len(pr_data.files)} files modified with {total_additions + total_deletions} total line changes, focusing on [infer from title] ...'",
  
  "purpose": "The ACTUAL technical problem being solved (cite issue numbers from description if present). Example: 'Fixes Issue #XXXXX where [specific problem from title/description]'",
  
  "testing_focus": [
    "SPECIFIC test scenario 1 based on actual changes (e.g., 'Open chat in untitled file, verify session initializes without null errors')",
    "SPECIFIC scenario 2 with edge case (e.g., 'Rename file during active session, confirm sessionId persists correctly')",
    "SPECIFIC scenario 3 for regression (e.g., 'Test existing saved-file workflow unchanged')"
  ],
  
  "potential_risks": [
    "SPECIFIC technical risk from THIS PR (e.g., 'Session API breaking change: sessionId now nullable during init - may break extensions expecting immediate ID')",
    "SPECIFIC concern with file reference (e.g., 'Large refactor in ErrorHandler.ts could introduce uncaught exceptions in error-handling code itself')"
  ],
  
  "affected_areas": [
    "Specific module/file with role (e.g., 'ChatSessionsService.ts - core session lifecycle')",
    "API/component changed (e.g., 'POST /api/sessions endpoint - validates sessionId')",
    "Database/state impact (e.g., 'Session storage schema - adds optional fallback_id field')"
  ],
  
  "review_priority": "HIGH/MEDIUM/LOW/CRITICAL with detailed justification. MUST reference actual change volume ({total_additions + total_deletions} lines, {len(pr_data.files)} files). Example: 'MEDIUM - Modifies {len(pr_data.files)} files with {total_additions + total_deletions} line changes in [area from title], affecting [component] with [risk level]'",
  
  "estimated_review_time": "Realistic minutes based on {total_additions + total_deletions} lines changed. Formula: <200 lines: 10-20min | 200-500: 20-40min | 500-1000: 40-70min | >1000: 70-120min. Adjust for complexity from title/description.",
  
  "key_changes": [
    "SPECIFIC technical change with file + impact (e.g., 'ChatSessionsService.ts: Adds async initSession() method with null-check, replaces sync constructor pattern - breaking change for direct instantiation')",
    "SPECIFIC change explaining architecture (e.g., 'Introduces SessionValidator middleware (+200 lines) enforcing sessionId validation before all API calls - new security layer')",
    "SPECIFIC change about performance/security (e.g., 'Removes N+1 query in getActiveSessions() by adding eager loading - 10x performance improvement')",
    "Continue with 2-5 more SPECIFIC items..."
  ]
}}

🔥 CRITICAL INSTRUCTIONS:
1. **USE ACTUAL NUMBERS**: STATS section shows {total_additions}+ additions, {total_deletions}- deletions, {total_additions + total_deletions} total lines - REFERENCE THESE EXACT NUMBERS in your analysis
2. **NEVER SAY**: "0 lines", "change volume is 0", "no files modified" when stats show otherwise
3. Use PR TITLE and DESCRIPTION to infer WHAT changed even if file names unavailable  
4. Cite ACTUAL FILES when available from FILES CHANGED list
5. Be SPECIFIC or don't mention it - NO generic advice whatsoever
6. {f"You have individual file names - use them!" if has_individual_files else "File names unavailable - infer from title/description/change volume"}

Return ONLY valid JSON. NO markdown, NO code blocks, NO extra text. Just the JSON object."""

        return prompt
    
    async def analyze_pr(self, pr_data: PRAnalyzeRequest, max_retries: int = 3) -> PRContext:
        """
        Analyze PR using Groq AI with retry logic and exponential backoff
        
        Args:
            pr_data: PR data to analyze
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            PRContext with analysis results
            
        Raises:
            ValueError: If analysis fails after all retries
            GroqError: If Groq API call fails permanently
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                prompt = self._build_analysis_prompt(pr_data)
                
                logger.info(f"Analyzing PR (attempt {attempt + 1}/{max_retries}): {pr_data.title}")
                logger.debug(f"Prompt length: {len(prompt)} characters")
                
                # Call Groq API
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert code reviewer. Respond only with valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,  # Lower temperature for more consistent output
                    max_tokens=2000,
                    top_p=0.9
                )
                
                # Extract response
                content = response.choices[0].message.content.strip()
                logger.debug(f"Groq response length: {len(content)} characters")
                
                # Parse JSON response
                try:
                    # Remove markdown code blocks if present
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                    
                    analysis_data = json.loads(content)
                    
                    # Validate and create PRContext
                    context = PRContext(**analysis_data)
                    logger.info(f"PR analysis completed successfully on attempt {attempt + 1}")
                    return context
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Raw response: {content}")
                    
                    # If this is the last attempt, use fallback
                    if attempt == max_retries - 1:
                        logger.warning("All retries exhausted, using fallback context")
                        return self._create_fallback_context(pr_data, content)
                    
                    # Otherwise, retry
                    last_error = e
                    continue
                
            except GroqError as e:
                logger.error(f"Groq API error on attempt {attempt + 1}: {e}")
                last_error = e
                
                # Check if it's a rate limit error
                error_str = str(e).lower()
                if "rate limit" in error_str or "quota" in error_str:
                    logger.warning("Rate limit detected, longer wait before retry")
                    if attempt < max_retries - 1:
                        wait_time = min(2 ** (attempt + 2), 30)  # Up to 30 seconds for rate limits
                        logger.info(f"Rate limit backoff: waiting {wait_time}s before retry {attempt + 2}")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ValueError(
                            "Groq API rate limit exceeded. Please try again in a few minutes. "
                            "Free tier: 80,000 tokens/day, 30 requests/minute."
                        )
                
                # Exponential backoff for other errors
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 10)  # Max 10 seconds between retries
                    logger.info(f"Waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"AI analysis failed after {max_retries} attempts: {str(e)}")
                    
            except Exception as e:
                logger.error(f"Unexpected error during PR analysis (attempt {attempt + 1}): {e}", exc_info=True)
                last_error = e
                
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 10)
                    logger.info(f"Waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Analysis failed after {max_retries} attempts: {str(e)}")
        
        # Should never reach here, but just in case
        raise ValueError(f"Analysis failed: {str(last_error)}")
    
    def _create_fallback_context(self, pr_data: PRAnalyzeRequest, raw_response: str) -> PRContext:
        """Create fallback context if JSON parsing fails"""
        logger.warning("Creating fallback context due to parsing error")
        
        total_changes = sum(f.additions + f.deletions for f in pr_data.files)
        
        # Estimate review time based on changes
        if total_changes < 50:
            review_time = "5-10 minutes"
            priority = "low"
        elif total_changes < 200:
            review_time = "15-25 minutes"
            priority = "medium"
        elif total_changes < 500:
            review_time = "30-45 minutes"
            priority = "high"
        else:
            review_time = "1+ hours"
            priority = "critical"
        
        return PRContext(
            summary=f"This PR modifies {len(pr_data.files)} files with {total_changes} total changes.",
            purpose=pr_data.description[:200] if pr_data.description else "No description provided",
            testing_focus=[
                "Test the modified functionality",
                "Check for breaking changes",
                "Verify edge cases"
            ],
            potential_risks=[
                "Changes may affect existing functionality",
                "Review for potential bugs"
            ],
            affected_areas=[f.filename.split('/')[0] for f in pr_data.files[:5]],
            review_priority=priority,
            estimated_review_time=review_time,
            key_changes=[f"{f.filename} ({f.status})" for f in pr_data.files[:5]]
        )


# Singleton instance
_groq_service: Optional[GroqService] = None


def get_groq_service() -> GroqService:
    """Get or create Groq service instance"""
    global _groq_service
    if _groq_service is None:
        _groq_service = GroqService()
    return _groq_service
