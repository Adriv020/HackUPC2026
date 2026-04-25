import asyncio

from websocket.manager import broadcast


async def watch_placements(db) -> None:
    """
    Watches bay_placements inserts via MongoDB change stream.
    Requires a replica set — Atlas M0 includes one; local dev needs mongod --replSet rs0.
    On error, restarts after 5s so a transient network blip doesn't kill the stream.
    """
    pipeline = [{"$match": {"operationType": "insert"}}]
    try:
        async with db.bay_placements.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                doc = change.get("fullDocument", {})
                sid = str(doc.get("scenarioId", ""))
                if sid:
                    await broadcast(sid, {"event": "placement_added", "scenarioId": sid})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Change stream error: {exc}. Restarting in 5s…")
        await asyncio.sleep(5)
        asyncio.create_task(watch_placements(db))
