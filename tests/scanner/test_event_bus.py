import unittest

from services.event_bus import EventTypes, get_event_bus
from services.event_bus.bus import InMemoryEventBus
from services.event_bus.events import Event


class TestEventBus(unittest.TestCase):
    def test_in_memory_publish_subscribe(self):
        bus = InMemoryEventBus()
        received: list[Event] = []

        async def handler(event: Event):
            received.append(event)

        import asyncio
        async def run():
            await bus.subscribe("test", handler)
            await bus.publish("test", Event(type=EventTypes.SCAN_COMPLETED, payload={"score": 80}))
        asyncio.run(run())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["score"], 80)


if __name__ == "__main__":
    unittest.main()
