from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any, AsyncIterator, Deque, List, Sequence, Set


class EventStore:
    """
    In-memory event store that records recent events and fan-outs new ones to
    subscribers via per-subscriber asyncio queues. The queues have bounded
    capacity so slow consumers exert back-pressure on producers.
    """

    def __init__(self, maxlen: int = 1_000, subscriber_queue_size: int = 256):
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        if subscriber_queue_size <= 0:
            raise ValueError("subscriber_queue_size must be positive")

        self._events: Deque[Any] = deque(maxlen=maxlen)
        self._subscriber_queue_size = subscriber_queue_size
        self._subscribers: Set[asyncio.Queue[Any]] = set()
        self._lock = threading.Lock()

    async def append(self, event: Any) -> None:
        """Store an event and publish it to all active subscribers."""
        with self._lock:
            self._events.append(event)
            subscribers: Sequence[asyncio.Queue[Any]] = tuple(self._subscribers)

        for queue in subscribers:
            await queue.put(event)

    def tail(self, n: int) -> List[Any]:
        """Return the latest ``n`` events (oldest first)."""
        if n <= 0:
            return []

        with self._lock:
            return list(self._events)[-n:]

    def subscribe(self) -> AsyncIterator[Any]:
        """
        Register a new subscriber and yield events as they arrive. Consumers can
        terminate the stream by breaking out of the async-iterator, which removes
        the underlying queue.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        with self._lock:
            self._subscribers.add(queue)

        async def iterator() -> AsyncIterator[Any]:
            try:
                while True:
                    event = await queue.get()
                    yield event
            finally:
                with self._lock:
                    self._subscribers.discard(queue)

        return iterator()
