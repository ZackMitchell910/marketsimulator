import asyncio

import pytest

from src.store.event_store import EventStore


@pytest.mark.asyncio
async def test_event_store_preserves_ordering():
    store = EventStore(maxlen=10, subscriber_queue_size=4)
    consumer = store.subscribe()
    received = []

    async def _consume():
        try:
            async for event in consumer:
                received.append(event)
                if len(received) == 3:
                    break
        finally:
            await consumer.aclose()

    consumer_task = asyncio.create_task(_consume())

    await store.append({"seq": 1})
    await store.append({"seq": 2})
    await store.append({"seq": 3})

    await consumer_task
    assert [event["seq"] for event in received] == [1, 2, 3]
    assert [event["seq"] for event in store.tail(2)] == [2, 3]


@pytest.mark.asyncio
async def test_event_store_backpressure_blocks_until_consumed():
    store = EventStore(maxlen=5, subscriber_queue_size=1)
    gen = store.subscribe()

    await store.append({"seq": 1})

    second_append = asyncio.create_task(store.append({"seq": 2}))
    await asyncio.sleep(0)
    assert not second_append.done()

    first = await gen.__anext__()
    assert first["seq"] == 1

    await asyncio.sleep(0)
    assert second_append.done()
    await second_append

    second = await gen.__anext__()
    assert second["seq"] == 2

    await gen.aclose()
