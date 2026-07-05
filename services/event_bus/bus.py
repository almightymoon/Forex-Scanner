"""Event bus — Redis Streams with in-memory fallback."""

import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Awaitable, Callable

from shared.configs.settings import get_settings

from .events import Event

settings = get_settings()
EventHandler = Callable[[Event], Awaitable[None]]


class EventBusBackend(ABC):
    @abstractmethod
    async def publish(self, stream: str, event: Event) -> str:
        ...

    @abstractmethod
    async def subscribe(self, stream: str, handler: EventHandler, group: str = "default") -> None:
        ...


class InMemoryEventBus(EventBusBackend):
    """Local fallback when Redis is unavailable."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._log: list[tuple[str, Event]] = []

    async def publish(self, stream: str, event: Event) -> str:
        self._log.append((stream, event))
        for handler in self._handlers.get(stream, []):
            await handler(event)
        return f"mem-{len(self._log)}"

    async def subscribe(self, stream: str, handler: EventHandler, group: str = "default") -> None:
        self._handlers[stream].append(handler)

    def history(self, stream: str | None = None) -> list[tuple[str, Event]]:
        if stream:
            return [(s, e) for s, e in self._log if s == stream]
        return list(self._log)


class RedisEventBus(EventBusBackend):
    """Redis Streams backend for production."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def publish(self, stream: str, event: Event) -> str:
        client = await self._get_client()
        msg_id = await client.xadd(stream, {"data": event.to_json()})
        return msg_id

    async def subscribe(self, stream: str, handler: EventHandler, group: str = "default") -> None:
        client = await self._get_client()
        consumer = f"c-{id(handler)}"
        try:
            await client.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass

        while True:
            results = await client.xreadgroup(group, consumer, {stream: ">"}, count=10, block=5000)
            for _stream, messages in results:
                for msg_id, fields in messages:
                    data = json.loads(fields["data"])
                    event = Event(type=data["type"], payload=data["payload"], timestamp=data["timestamp"])
                    await handler(event)
                    await client.xack(stream, group, msg_id)
            await asyncio.sleep(0.1)


class EventBus:
    """Facade — auto-selects Redis or in-memory backend."""

    def __init__(self, backend: EventBusBackend | None = None):
        self._backend = backend or self._create_backend()

    def _create_backend(self) -> EventBusBackend:
        try:
            import redis
            client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            client.ping()
            return RedisEventBus(settings.REDIS_URL)
        except Exception:
            return InMemoryEventBus()

    @property
    def backend(self) -> EventBusBackend:
        return self._backend

    async def publish(self, stream: str, event_type: str, payload: dict, source: str = "scanner") -> str:
        event = Event(type=event_type, payload=payload, source=source)
        return await self._backend.publish(stream, event)

    async def on(self, stream: str, handler: EventHandler) -> None:
        await self._backend.subscribe(stream, handler)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
