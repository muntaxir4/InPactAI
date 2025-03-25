from fastapi import APIRouter, WebSocket, Depends, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
import json
from db.db import get_db
from models.chat import ChatMessage, MessageStatus
from services.chat_services import chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket, user_id: str, db: AsyncSession = Depends(get_db)
):
    await chat_service.connect(user_id, websocket, db)
    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("event_type", "")
            if event_type == "GET_CHAT_LIST":
                chat_list = await chat_service.get_chat_list(user_id, db)
                await websocket.send_json(chat_list)

            elif event_type == "SEND_MESSAGE":
                # Send message to receiver if online
                data["sender_id"] = user_id
                await chat_service.send_message(data, db)

            elif event_type == "USER_STATUS":
                target_user_id = data.get("target_user_id")
                is_online = chat_service.is_user_online(target_user_id)
                await websocket.send_json(
                    {
                        "event_type": "USER_STATUS",
                        "target_user_id": target_user_id,
                        "is_online": is_online,
                    }
                )
    except WebSocketDisconnect:
        chat_service.disconnect(user_id, db)


@router.get("/{user_id}/{receiver_id}")
async def get_chat_history(
    user_id: str, receiver_id: str, db: AsyncSession = Depends(get_db)
):
    return await chat_service.get_chat_history(user_id, receiver_id, db)


@router.put("/read/{user_id}/{receiver_id}")
async def mark_as_read(
    user_id: str, receiver_id: str, db: AsyncSession = Depends(get_db)
):
    await chat_service.mark_as_read(user_id, receiver_id, db)

    return {"message": "Messages marked as read"}
