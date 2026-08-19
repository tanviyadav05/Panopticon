"""WebSocket: pushes telemetry AND target status over /ws/live.
Message types: {"type":"backlog"|"update","events":[...]}
               {"type":"targets_update","targets":[...]}
"""
from __future__ import annotations
import asyncio, os, sys
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telemetry_api import store, _get_registry

router = APIRouter()
TELEMETRY_POLL = 0.3
TARGETS_POLL   = 3.0


@router.websocket("/ws/live")
async def live_telemetry(websocket: WebSocket):
    await websocket.accept()
    backlog = store.recent(100)
    cursor  = store._cursor
    try:
        if backlog:
            await websocket.send_json({"type": "backlog", "events": [e.model_dump() for e in backlog]})
        try:
            await websocket.send_json({"type": "targets_update", "targets": _get_registry().as_list()})
        except Exception:
            pass

        target_acc = 0.0
        while True:
            await asyncio.sleep(TELEMETRY_POLL)
            target_acc += TELEMETRY_POLL

            new_events, cursor = store.since(cursor)
            if new_events:
                await websocket.send_json({"type": "update", "events": [e.model_dump() for e in new_events]})

            if target_acc >= TARGETS_POLL:
                target_acc = 0.0
                try:
                    await websocket.send_json({"type": "targets_update", "targets": _get_registry().as_list()})
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
