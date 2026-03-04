"""Pydantic models for request/response validation"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class PRFile(BaseModel):
    """Represents a file changed in the PR"""
    filename: str = Field(..., description="File path")
    status: str = Field(..., description="File status: added, modified, removed, renamed")
    additions: int = Field(default=0, description="Number of lines added")
    deletions: int = Field(default=0, description="Number of lines deleted")
    changes: int = Field(default=0, description="Total changes")
    patch: Optional[str] = Field(default=None, description="Git diff patch")


class PRCommit(BaseModel):
    """Represents a commit in the PR"""
    sha: str = Field(..., description="Commit SHA")
    message: str = Field(..., description="Commit message")
    author: str = Field(..., description="Commit author")


class PRAnalyzeRequest(BaseModel):
    """Request model for PR analysis"""
    title: str = Field(..., min_length=1, max_length=500, description="PR title")
    description: Optional[str] = Field(default="", description="PR description/body")
    files: List[PRFile] = Field(..., min_items=1, description="Changed files")
    commits: Optional[List[PRCommit]] = Field(default=[], description="PR commits")
    base_branch: Optional[str] = Field(default="main", description="Base branch")
    head_branch: Optional[str] = Field(default="", description="Head branch")
    pr_url: Optional[str] = Field(default="", description="PR URL")
    
    @validator('files')
    def validate_files(cls, v):
        if len(v) > 100:
            raise ValueError("Too many files. Maximum 100 files allowed.")
        return v
    
    @validator('description')
    def validate_description(cls, v):
        if v and len(v) > 10000:
            return v[:10000] + "... (truncated)"
        return v or ""


class PRContext(BaseModel):
    """Generated PR context response"""
    summary: str = Field(..., description="High-level summary of changes")
    purpose: str = Field(..., description="Purpose and intent of the PR")
    testing_focus: List[str] = Field(..., description="Areas to focus on during testing")
    potential_risks: List[str] = Field(..., description="Potential risks or concerns")
    affected_areas: List[str] = Field(..., description="Code areas affected")
    review_priority: str = Field(..., description="Priority level: low, medium, high, critical")
    estimated_review_time: str = Field(..., description="Estimated time to review")
    key_changes: List[str] = Field(..., description="Most important changes")


class PRAnalyzeResponse(BaseModel):
    """Response model for PR analysis"""
    success: bool = Field(..., description="Whether analysis succeeded")
    context: Optional[PRContext] = Field(default=None, description="Generated context")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")
