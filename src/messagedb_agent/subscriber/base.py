"""Generic subscriber framework for Message DB event streams."""

import asyncio
import time
from collections.abc import Awaitable
from typing import Protocol

import structlog

from messagedb_agent.store import MessageDBClient
from messagedb_agent.store.category import get_category_messages
from messagedb_agent.store.operations import Message

logger = structlog.get_logger(__name__)


class SubscriberError(Exception):
    """Exception raised for subscriber-related errors."""

    pass


class MessageHandler(Protocol):
    """Protocol for message handlers that process messages.

    Handlers can be either synchronous or asynchronous functions that
    accept a Message and return None.
    """

    def __call__(self, message: Message) -> None | Awaitable[None]:
        """Process a message.

        Args:
            message: The message to process

        Returns:
            None for synchronous handlers, Awaitable[None] for async handlers
        """
        ...


class Subscriber:
    """Generic subscriber for Message DB category streams.

    The subscriber polls a category stream and invokes a handler for each event.
    It tracks position and supports both synchronous and asynchronous handlers.

    Example:
        >>> def my_handler(message: Message) -> None:
        ...     print(f"Received {message.type}: {message.data}")
        ...
        >>> client = MessageDBClient(config)
        >>> subscriber = Subscriber(
        ...     category="agent",
        ...     handler=my_handler,
        ...     store_client=client,
        ...     poll_interval_ms=100,
        ...     batch_size=1000
        ... )
        >>> subscriber.start()  # Runs until stopped
    """

    def __init__(
        self,
        category: str,
        handler: MessageHandler,
        store_client: MessageDBClient,
        poll_interval_ms: int = 100,
        batch_size: int = 1000,
    ):
        """Initialize the subscriber.

        Args:
            category: The Message DB category to subscribe to
            handler: Function to call for each event (sync or async)
            store_client: Message DB client for reading events
            poll_interval_ms: Time to wait between polls in milliseconds
            batch_size: Maximum number of events to fetch per poll
        """
        self.category = category
        self.handler = handler
        self.store_client = store_client
        self.poll_interval_ms = poll_interval_ms
        self.batch_size = batch_size
        self.position = 0
        self._should_stop = False
        self._is_running = False

        # Detect if handler is async
        self._is_async_handler = asyncio.iscoroutinefunction(handler)

        logger.info(
            "subscriber_initialized",
            category=category,
            poll_interval_ms=poll_interval_ms,
            batch_size=batch_size,
            is_async=self._is_async_handler,
        )

    def start(self) -> None:
        """Start the subscriber polling loop.

        This method blocks until stop() is called or an unrecoverable error occurs.
        Individual message processing errors are logged but do not stop the subscriber.

        Raises:
            SubscriberError: If subscriber is already running or encounters fatal error
        """
        if self._is_running:
            raise SubscriberError("Subscriber is already running")

        self._should_stop = False
        self._is_running = True

        logger.info("subscriber_starting", category=self.category, position=self.position)

        try:
            if self._is_async_handler:
                # Run async polling loop
                asyncio.run(self._async_polling_loop())
            else:
                # Run sync polling loop
                self._sync_polling_loop()
        except Exception as e:
            logger.error(
                "subscriber_fatal_error",
                category=self.category,
                error=str(e),
                exc_info=True,
            )
            raise SubscriberError(f"Fatal error in subscriber: {e}") from e
        finally:
            self._is_running = False
            logger.info("subscriber_stopped", category=self.category, position=self.position)

    def stop(self) -> None:
        """Request graceful shutdown of the subscriber.

        The subscriber will finish processing the current batch and then stop.
        """
        logger.info("subscriber_stop_requested", category=self.category)
        self._should_stop = True

    def _sync_polling_loop(self) -> None:
        """Synchronous polling loop for sync handlers."""
        while not self._should_stop:
            try:
                # Fetch batch of messages
                messages = get_category_messages(
                    client=self.store_client,
                    category=self.category,
                    position=self.position,
                    batch_size=self.batch_size,
                )

                if messages:
                    logger.debug(
                        "subscriber_batch_received",
                        category=self.category,
                        count=len(messages),
                        position=self.position,
                    )

                    # Process each message
                    for message in messages:
                        try:
                            self.handler(message)
                        except Exception as e:
                            logger.error(
                                "handler_error",
                                category=self.category,
                                message_type=message.type,
                                stream_name=message.stream_name,
                                position=message.position,
                                global_position=message.global_position,
                                error=str(e),
                                exc_info=True,
                            )
                            # Continue processing despite handler error

                    # Update position to highest global_position + 1
                    max_global_position = max(m.global_position for m in messages)
                    self.position = max_global_position + 1

                    logger.debug(
                        "subscriber_position_updated",
                        category=self.category,
                        position=self.position,
                    )
                else:
                    # No messages, just log at trace level
                    logger.debug(
                        "subscriber_no_messages",
                        category=self.category,
                        position=self.position,
                    )

                # Sleep before next poll
                time.sleep(self.poll_interval_ms / 1000.0)

            except Exception as e:
                logger.error(
                    "subscriber_polling_error",
                    category=self.category,
                    position=self.position,
                    error=str(e),
                    exc_info=True,
                )
                # Sleep before retrying
                time.sleep(self.poll_interval_ms / 1000.0)

    async def _async_polling_loop(self) -> None:
        """Asynchronous polling loop for async handlers."""
        while not self._should_stop:
            try:
                # Fetch batch of messages (sync operation)
                messages = get_category_messages(
                    client=self.store_client,
                    category=self.category,
                    position=self.position,
                    batch_size=self.batch_size,
                )

                if messages:
                    logger.debug(
                        "subscriber_batch_received",
                        category=self.category,
                        count=len(messages),
                        position=self.position,
                    )

                    # Process each message
                    for message in messages:
                        try:
                            result = self.handler(message)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(
                                "handler_error",
                                category=self.category,
                                message_type=message.type,
                                stream_name=message.stream_name,
                                position=message.position,
                                global_position=message.global_position,
                                error=str(e),
                                exc_info=True,
                            )
                            # Continue processing despite handler error

                    # Update position to highest global_position + 1
                    max_global_position = max(m.global_position for m in messages)
                    self.position = max_global_position + 1

                    logger.debug(
                        "subscriber_position_updated",
                        category=self.category,
                        position=self.position,
                    )
                else:
                    # No messages, just log at trace level
                    logger.debug(
                        "subscriber_no_messages",
                        category=self.category,
                        position=self.position,
                    )

                # Sleep before next poll
                await asyncio.sleep(self.poll_interval_ms / 1000.0)

            except Exception as e:
                logger.error(
                    "subscriber_polling_error",
                    category=self.category,
                    position=self.position,
                    error=str(e),
                    exc_info=True,
                )
                # Sleep before retrying
                await asyncio.sleep(self.poll_interval_ms / 1000.0)
