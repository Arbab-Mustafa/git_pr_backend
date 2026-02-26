"""PR Analysis endpoints"""

import logging
import time
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models import PRAnalyzeRequest, PRAnalyzeResponse, ErrorResponse, PRContext
from app.services import get_groq_service, get_cache_service
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/analyze",
    response_model=PRAnalyzeResponse,
    summary="Analyze GitHub PR",
    description="Generate AI-powered context for a GitHub Pull Request"
)
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
async def analyze_pr(request: Request, pr_data: PRAnalyzeRequest):
    """
    Analyze a GitHub Pull Request and generate comprehensive context
    
    - **title**: PR title
    - **description**: PR description/body
    - **files**: List of changed files with diffs
    - **commits**: List of commits (optional)
    - **base_branch**: Base branch name
    - **head_branch**: Head branch name
    
    Returns structured context including:
    - Summary of changes
    - Purpose and intent
    - Testing focus areas
    - Potential risks
    - Affected code areas
    - Review priority
    - Estimated review time
    """
    start_time = time.time()
    
    try:
        logger.info(f"Received PR analysis request: {pr_data.title}")
        logger.info(f"Files: {len(pr_data.files)}, Commits: {len(pr_data.commits)}")
        
        # Check cache first
        cache_service = get_cache_service()
        cached_context = cache_service.get(pr_data)
        
        if cached_context:
            elapsed_time = time.time() - start_time
            logger.info(f"Returning CACHED result in {elapsed_time:.2f}s")
            
            return PRAnalyzeResponse(
                success=True,
                context=cached_context,
                metadata={
                    "processing_time": f"{elapsed_time:.2f}s",
                    "files_analyzed": len(pr_data.files),
                    "commits_analyzed": len(pr_data.commits),
                    "model": settings.GROQ_MODEL,
                    "cached": True
                }
            )
        
        # Validate request
        if not pr_data.files:
            raise HTTPException(
                status_code=400,
                detail="At least one file must be provided"
            )
        
        # Get Groq service
        try:
            groq_service = get_groq_service()
        except ValueError as e:
            logger.error(f"Groq service initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=str(e)
            )
        
        # Analyze PR
        try:
            context = await groq_service.analyze_pr(pr_data)
            
            # Cache the successful result
            cache_service.set(pr_data, context)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Analysis completed in {elapsed_time:.2f}s")
            
            return PRAnalyzeResponse(
                success=True,
                context=context,
                metadata={
                    "processing_time": f"{elapsed_time:.2f}s",
                    "files_analyzed": len(pr_data.files),
                    "commits_analyzed": len(pr_data.commits),
                    "model": settings.GROQ_MODEL,
                    "cached": False
                }
            )
            
        except ValueError as e:
            logger.error(f"Analysis failed: {e}")
            raise HTTPException(
                status_code=422,
                detail=f"Analysis failed: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in analyze_pr: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during analysis"
        )


@router.post(
    "/analyze/quick",
    response_model=PRAnalyzeResponse,
    summary="Quick PR Analysis (30 seconds mode)",
    description="Generate a quick summary for fast reviews"
)
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
async def quick_analyze_pr(request: Request, pr_data: PRAnalyzeRequest):
    """
    Quick PR analysis for fast reviews
    Returns abbreviated context focusing on key points only
    """
    start_time = time.time()
    
    try:
        # Simplified analysis - only use first few files
        simplified_data = pr_data.model_copy()
        simplified_data.files = pr_data.files[:10]  # Only first 10 files
        simplified_data.commits = pr_data.commits[:5]  # Only first 5 commits
        
        groq_service = get_groq_service()
        context = await groq_service.analyze_pr(simplified_data)
        
        elapsed_time = time.time() - start_time
        
        return PRAnalyzeResponse(
            success=True,
            context=context,
            metadata={
                "processing_time": f"{elapsed_time:.2f}s",
                "mode": "quick",
                "files_analyzed": len(simplified_data.files),
                "total_files": len(pr_data.files)
            }
        )
        
    except Exception as e:
        logger.error(f"Quick analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Quick analysis failed: {str(e)}"
        )
