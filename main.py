"""
GitHub PR Context Generator - Backend API
FastAPI server with Groq AI integration and autonomous agent system
"""

import os
import sys
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Validate startup BEFORE importing app modules
try:
    from app.startup_validator import validate_startup
    validate_startup()
except Exception as e:
    # If validation fails, print error and exit
    print(f"\n{'='*60}")
    print("❌ STARTUP VALIDATION FAILED")
    print(f"{'='*60}")
    print(f"\n{str(e)}\n")
    print("Cannot start server. Fix the issues above and try again.")
    print(f"{'='*60}\n")
    sys.exit(1)

# Import routers (after validation)
from app.routers import analyze
from app.routers import agent_routes
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        # In production, also log to file
        # logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Rate limiter (with error handling)
try:
    limiter = Limiter(key_func=get_remote_address)
except Exception as e:
    logger.error(f"Failed to initialize rate limiter: {e}")
    logger.warning("Starting without rate limiting (not recommended for production)")
    limiter = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("="*60)
    logger.info("🚀 Starting PR Context Generator API")
    logger.info("="*60)
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Allowed origins: {settings.ALLOWED_ORIGINS}")
    logger.info(f"Groq API: {'✅ Configured' if settings.GROQ_API_KEY else '❌ Missing'}")
    logger.info(f"GitHub API: {'✅ Configured' if settings.GITHUB_TOKEN else '❌ Missing'}")
    logger.info(f"Agent system: {'✅ Enabled' if settings.GITHUB_TOKEN else '⚠️ Disabled (no GitHub token)'}")
    logger.info("="*60)
    
    yield
    
    logger.info("="*60)
    logger.info("🛑 Shutting down PR Context Generator API")
    logger.info("="*60)


# Initialize FastAPI app
app = FastAPI(
    title="PR Context Generator API",
    description="AI-powered GitHub PR context analysis using Groq",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add rate limiter (if available)
if limiter:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - use regex to match chrome-extension origins
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions with production-grade error responses"""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    
    # Determine if this is a client error or server error
    status_code = 500
    error_type = "Internal Server Error"
    
    if isinstance(exc, ValueError):
        status_code = 400
        error_type = "Bad Request"
    elif isinstance(exc, PermissionError):
        status_code = 403
        error_type = "Forbidden"
    elif isinstance(exc, FileNotFoundError):
        status_code = 404
        error_type = "Not Found"
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_type,
            "message": "An error occurred processing your request.",
            "detail": str(exc) if settings.DEBUG else "Enable DEBUG mode for details",
            "path": str(request.url.path),
            "timestamp": str(datetime.now().isoformat()) if settings.DEBUG else None
        }
    )


# Health check endpoint
@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "PR Context Generator API",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check with component status"""
    from datetime import datetime
    
    groq_configured = bool(settings.GROQ_API_KEY and settings.GROQ_API_KEY != "your_groq_api_key_here")
    github_configured = bool(settings.GITHUB_TOKEN and settings.GITHUB_TOKEN != "your_github_token_here")
    
    # Determine overall health status
    if groq_configured and github_configured:
        status = "healthy"
    elif groq_configured:
        status = "degraded"  # Can analyze PRs but can't use agents
    else:
        status = "unhealthy"  # Missing critical config
    
    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "components": {
            "api": "up",
            "groq_llm": "configured" if groq_configured else "not_configured",
            "github_api": "configured" if github_configured else "not_configured",
            "agent_system": "enabled" if github_configured else "disabled",
            "rate_limiter": "enabled" if limiter else "disabled"
        },
        "features": {
            "pr_analysis": groq_configured,
            "autonomous_agents": groq_configured and github_configured,
            "github_integration": github_configured
        },
        "environment": "development" if settings.DEBUG else "production",
        "debug": settings.DEBUG
    }


@app.get("/privacy", tags=["Static"])
async def privacy_policy():
    """Serve privacy policy HTML"""
    import os
    privacy_path = os.path.join(os.path.dirname(__file__), "privacy.html")
    if os.path.exists(privacy_path):
        return FileResponse(privacy_path, media_type="text/html")
    return {"error": "Privacy policy not found"}


# Include routers
app.include_router(analyze.router, prefix="/api/v1", tags=["Analyze"])
app.include_router(agent_routes.router, prefix="/api/v1", tags=["AI Agent"])


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )
