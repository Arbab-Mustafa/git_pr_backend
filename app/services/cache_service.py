"""
Response caching service to reduce API calls and improve performance
"""

import hashlib
import json
import time
import logging
from typing import Optional, Dict, Any
from app.models import PRAnalyzeRequest, PRContext

logger = logging.getLogger(__name__)


class CacheService:
    """In-memory cache for PR analysis results"""
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache service
        
        Args:
            ttl_seconds: Time-to-live for cache entries (default: 1 hour)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
        logger.info(f"Cache service initialized with TTL: {ttl_seconds}s")
    
    def _generate_cache_key(self, pr_data: PRAnalyzeRequest) -> str:
        """
        Generate unique cache key from PR data
        
        Uses title, file count, and total changes to create hash
        This means same PR with same changes = cache hit
        """
        # Create deterministic representation
        cache_input = {
            "title": pr_data.title,
            "files": len(pr_data.files),
            "total_additions": sum(f.additions for f in pr_data.files),
            "total_deletions": sum(f.deletions for f in pr_data.files),
            # Include first 3 filenames for more specificity
            "sample_files": [f.filename for f in pr_data.files[:3]]
        }
        
        # Generate SHA256 hash
        cache_str = json.dumps(cache_input, sort_keys=True)
        cache_key = hashlib.sha256(cache_str.encode()).hexdigest()[:16]
        
        logger.debug(f"Generated cache key: {cache_key} for PR: {pr_data.title}")
        return cache_key
    
    def get(self, pr_data: PRAnalyzeRequest) -> Optional[PRContext]:
        """
        Get cached analysis if available and not expired
        
        Returns:
            Cached PRContext or None if not found/expired
        """
        cache_key = self._generate_cache_key(pr_data)
        
        if cache_key not in self._cache:
            logger.debug(f"Cache MISS for key: {cache_key}")
            return None
        
        entry = self._cache[cache_key]
        age = time.time() - entry["timestamp"]
        
        # Check if expired
        if age > self._ttl:
            logger.info(f"Cache EXPIRED for key: {cache_key} (age: {age:.1f}s)")
            del self._cache[cache_key]
            return None
        
        logger.info(f"Cache HIT for key: {cache_key} (age: {age:.1f}s)")
        return entry["data"]
    
    def set(self, pr_data: PRAnalyzeRequest, context: PRContext):
        """
        Store analysis result in cache
        """
        cache_key = self._generate_cache_key(pr_data)
        
        self._cache[cache_key] = {
            "data": context,
            "timestamp": time.time(),
            "pr_title": pr_data.title
        }
        
        logger.info(f"Cached analysis for key: {cache_key} (PR: {pr_data.title})")
        
        # Optional: Cleanup old entries (prevent memory bloat)
        self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry["timestamp"] > self._ttl
        ]
        
        for key in expired_keys:
            logger.debug(f"Removing expired cache entry: {key}")
            del self._cache[key]
    
    def clear(self):
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = time.time()
        entries = []
        
        for key, entry in self._cache.items():
            age = now - entry["timestamp"]
            entries.append({
                "key": key,
                "age_seconds": int(age),
                "pr_title": entry.get("pr_title", "Unknown")
            })
        
        return {
            "total_entries": len(self._cache),
            "ttl_seconds": self._ttl,
            "entries": entries
        }


# Global cache instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get singleton cache service instance"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService(ttl_seconds=3600)  # 1 hour default
    return _cache_service
