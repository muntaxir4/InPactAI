from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from datetime import datetime, timezone
from models.models import User
from models.chat import ChatMessage, MessageStatus
from typing import Dict
import json


class ChatService:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket, db: AsyncSession):
        """Accept WebSocket connection and update user status to online."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        # Mark user as online
        user = await db.get(User, user_id)
        if user:
            print(f"User {user_id} is online")
            user.is_online = True
            await db.commit()

    def disconnect(self, user_id: str, db: AsyncSession):
        """Remove connection and update last seen."""
        self.active_connections.pop(user_id, None)

        # Mark user as offline and update last seen
        user = db.get(User, user_id)
        if user:
            user.is_online = False
            user.last_seen = datetime.now(timezone.utc)
            db.commit()

    async def send_message(self, content: Dict[str, str]):
        """Send a message to the receiver if they are online."""
        receiver_id = content.get("receiver_id")
        if receiver_id in self.active_connections:
            await self.active_connections[receiver_id].send_json(content)

    async def get_chat_history(self, user_id: str, receiver_id: str, db: AsyncSession):
        """Fetch chat history between two users."""
        result = await db.execute(
            select(ChatMessage)
            .where(
                (
                    (ChatMessage.sender_id == user_id)
                    & (ChatMessage.receiver_id == receiver_id)
                )
                | (
                    (ChatMessage.sender_id == receiver_id)
                    & (ChatMessage.receiver_id == user_id)
                )
            )
            .order_by(ChatMessage.created_at)
        )
        messages = result.scalars().all()
        return messages

    async def mark_as_read(self, sender_id: str, receiver_id: str, db: AsyncSession):
        """Mark messages as read and notify sender."""
        result = await db.execute(
            select(ChatMessage).where(
                (ChatMessage.sender_id == sender_id)
                & (ChatMessage.receiver_id == receiver_id)
                & (ChatMessage.status != MessageStatus.SEEN)
            )
        )
        messages = result.scalars().all()

        for message in messages:
            message.status = MessageStatus.SEEN

        await db.commit()

        # Notify sender that messages are read
        await self.send_message({"receiver_id": sender_id, "status": "seen"})


chat_service = ChatService()
