from collections import defaultdict

from fastapi import WebSocket

connected: dict[str, set[WebSocket]] = defaultdict(set)


async def broadcast(scenario_id: str, message: dict) -> None:
    for ws in list(connected.get(scenario_id, [])):
        try:
            await ws.send_json(message)
        except Exception:
            connected[scenario_id].discard(ws)
