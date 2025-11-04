"""Display module for rendering agent events to HTML.

This module provides FastAPI service for rendering event streams as HTML,
combining agent message processing with LLM-generated displays.
"""

from messagedb_agent.display.models import RenderRequest, RenderResponse
from messagedb_agent.display.service import create_app

__all__ = ["RenderRequest", "RenderResponse", "create_app"]
