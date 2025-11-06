"""Agent invocation logic for the display service.

This module handles running the agent processing loop in response to user messages.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import structlog

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.engine.loop import process_thread
from messagedb_agent.llm import create_llm_client
from messagedb_agent.store import MessageDBClient
from messagedb_agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


async def run_agent_step(
    thread_id: str,
    store_client: MessageDBClient,
    llm_config: VertexAIConfig,
    auto_approve_tools: bool = True,
) -> None:
    """Run one or more agent steps to process the latest user message.

    This runs the standard agent loop:
    1. Read events from stream
    2. Project to agent state/context
    3. Determine next step (LLM, tool, or done)
    4. Execute step and write result events
    5. Repeat until agent is done

    Args:
        thread_id: Unique identifier for the conversation thread
        store_client: Message DB client to use (shared with display service for
            real-time visibility)
        llm_config: LLM configuration for agent
        auto_approve_tools: Whether to automatically approve tool executions
            (default: True for API service)

    Raises:
        ProcessingError: If agent processing fails
    """
    log = logger.bind(thread_id=thread_id, auto_approve_tools=auto_approve_tools)
    log.info("Starting agent processing")

    stream_name = f"agent:v0-{thread_id}"

    # Create LLM client and tool registry (reuse provided store_client)
    llm_client = create_llm_client(llm_config)
    tool_registry = ToolRegistry()

    # TODO: Register display preference tools when implemented
    # (messagedb-agent-112)

    # Run agent processing loop in thread pool to avoid blocking async event loop
    # This allows the polling loop to run concurrently and see events in real-time
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as executor:
        final_state = await loop.run_in_executor(
            executor,
            process_thread,
            thread_id,
            stream_name,
            store_client,
            llm_client,
            tool_registry,
            100,  # max_iterations
            auto_approve_tools,
        )

    log.info(
        "Agent processing complete",
        final_status=final_state.status.value,
        message_count=final_state.message_count,
        llm_call_count=final_state.llm_call_count,
        tool_call_count=final_state.tool_call_count,
    )
