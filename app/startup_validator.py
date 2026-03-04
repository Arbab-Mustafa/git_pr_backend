"""
Production-Grade Startup Validation
Validates critical dependencies, configuration, and services before server starts
"""

import logging
import sys
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class StartupValidationError(Exception):
    """Critical error that prevents application startup"""
    pass


class StartupValidator:
    """Validates all critical components before application starts"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """
        Run all validation checks
        Returns True if all critical checks pass
        Raises StartupValidationError if any critical check fails
        """
        logger.info("🔍 Running startup validation...")
        
        # Critical checks (must pass)
        self._validate_python_dependencies()
        self._validate_configuration()
        self._validate_environment_variables()
        
        # Non-critical checks (warnings only)
        self._check_optional_dependencies()
        self._check_configuration_security()
        
        # Report results
        if self.errors:
            error_msg = self._format_errors()
            logger.error(f"\n{error_msg}")
            raise StartupValidationError(error_msg)
        
        if self.warnings:
            warning_msg = self._format_warnings()
            logger.warning(f"\n{warning_msg}")
        
        logger.info("✅ Startup validation passed!")
        return True
    
    def _validate_python_dependencies(self):
        """Validate all required Python packages are installed"""
        required = {
            'fastapi': 'fastapi',
            'uvicorn': 'uvicorn',
            'groq': 'groq',
            'github': 'PyGithub',  # import name: package name
            'dotenv': 'python-dotenv',
            'pydantic': 'pydantic',
            'pydantic_settings': 'pydantic-settings',
            'slowapi': 'slowapi',
        }
        
        missing = []
        for import_name, package_name in required.items():
            try:
                __import__(import_name)
            except ImportError:
                missing.append(package_name)
        
        if missing:
            self.errors.append(
                f"❌ Missing required dependencies:\n"
                f"   {', '.join(missing)}\n"
                f"\n   Fix:\n"
                f"   pip install -r requirements.txt\n"
                f"   OR\n"
                f"   pip install {' '.join(missing)}"
            )
    
    def _validate_configuration(self):
        """Validate app configuration is valid"""
        try:
            from app.config import settings
            
            # Check critical settings
            if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "":
                self.errors.append(
                    "❌ GROQ_API_KEY not configured\n"
                    "\n   Fix:\n"
                    "   1. Create/edit .env file\n"
                    "   2. Add: GROQ_API_KEY=your_api_key_here\n"
                    "   3. Get key from: https://console.groq.com/keys"
                )
            
            if not settings.GITHUB_TOKEN or settings.GITHUB_TOKEN == "":
                self.errors.append(
                    "❌ GITHUB_TOKEN not configured (required for agents)\n"
                    "\n   Fix:\n"
                    "   1. Create GitHub Personal Access Token\n"
                    "   2. Add to .env: GITHUB_TOKEN=ghp_your_token\n"
                    "   3. Token needs: repo, pull_request permissions"
                )
            
        except Exception as e:
            self.errors.append(f"❌ Configuration validation failed: {str(e)}")
    
    def _validate_environment_variables(self):
        """Validate critical environment variables"""
        import os
        from pathlib import Path
        
        # Check if .env file exists
        env_path = Path(__file__).parent.parent / '.env'
        if not env_path.exists():
            self.warnings.append(
                "⚠️  No .env file found\n"
                f"   Expected: {env_path}\n"
                "   Using defaults (may not work correctly)"
            )
    
    def _check_optional_dependencies(self):
        """Check optional dependencies"""
        optional = {
            'openai': 'OpenAI (alternative LLM provider)',
            'redis': 'Redis (production memory)',
            'psycopg2': 'PostgreSQL (production database)',
        }
        
        for import_name, description in optional.items():
            try:
                __import__(import_name)
            except ImportError:
                # Not an error, just informational
                pass
    
    def _check_configuration_security(self):
        """Check for insecure configuration"""
        try:
            from app.config import settings
            
            # Warn if using default/placeholder values
            if settings.GROQ_API_KEY and 'your_' in settings.GROQ_API_KEY.lower():
                self.warnings.append(
                    "⚠️  GROQ_API_KEY looks like a placeholder value"
                )
            
            if settings.GITHUB_TOKEN and 'your_' in settings.GITHUB_TOKEN.lower():
                self.warnings.append(
                    "⚠️  GITHUB_TOKEN looks like a placeholder value"
                )
            
            # Warn if DEBUG is enabled (production concern)
            if settings.DEBUG:
                self.warnings.append(
                    "⚠️  DEBUG mode is enabled (disable in production)"
                )
        except Exception:
            pass
    
    def _format_errors(self) -> str:
        """Format error messages for display"""
        lines = [
            "=" * 60,
            "❌ STARTUP VALIDATION FAILED",
            "=" * 60,
            "",
            "The following critical errors must be fixed:",
            ""
        ]
        
        for i, error in enumerate(self.errors, 1):
            lines.append(f"{i}. {error}")
            lines.append("")
        
        lines.extend([
            "=" * 60,
            "Cannot start server until these are resolved.",
            "=" * 60,
        ])
        
        return "\n".join(lines)
    
    def _format_warnings(self) -> str:
        """Format warning messages for display"""
        lines = [
            "",
            "⚠️  STARTUP WARNINGS:",
            "-" * 60,
        ]
        
        for warning in self.warnings:
            lines.append(f"• {warning}")
            lines.append("")
        
        lines.append("-" * 60)
        
        return "\n".join(lines)


def validate_startup() -> bool:
    """
    Main entry point for startup validation
    Returns True if validation passes, raises StartupValidationError otherwise
    """
    validator = StartupValidator()
    return validator.validate_all()


# For testing validation directly
if __name__ == "__main__":
    try:
        validate_startup()
        print("\n✅ All checks passed! Server is ready to start.")
        sys.exit(0)
    except StartupValidationError as e:
        print(str(e))
        sys.exit(1)
