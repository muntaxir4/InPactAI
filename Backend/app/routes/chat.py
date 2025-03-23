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
        print(f"User {user_id} connected")
        while True:
            data = await websocket.receive_json()
            receiver_id = data.get("receiver_id")
            message_text = data.get("message")

            # Store message in DB
            new_message = ChatMessage(
                sender_id=user_id,
                receiver_id=receiver_id,
                message=message_text,
                status=MessageStatus.SENT,
            )
            db.add(new_message)
            await db.commit()

            # Send message to receiver if online
            await chat_service.send_message(
                {
                    "receiver_id": receiver_id,
                    "sender_id": user_id,
                    "message": message_text,
                    "status": "delivered",
                },
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
