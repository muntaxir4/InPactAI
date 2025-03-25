from fastapi import WebSocket, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from datetime import datetime, timezone
from models.models import User
from models.chat import ChatList, ChatMessage, MessageStatus
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

    async def send_message(self, data: Dict[str, str], db: AsyncSession):
        """Send a message to the receiver if they are online."""
        receiver_id = data.get("receiver_id")
        sender_id = data.get("sender_id")
        message_text = data.get("message")

        # Find or create chat list
        chat_list = await db.execute(
            select(ChatList).where(
                ((ChatList.user1_id == sender_id) & (ChatList.user2_id == receiver_id))
                | (
                    (ChatList.user1_id == receiver_id)
                    & (ChatList.user2_id == sender_id)
                )
            )
        )
        chat_list = chat_list.scalar_one_or_none()

        if not chat_list:
            chat_list = ChatList(user1_id=sender_id, user2_id=receiver_id)
            db.add(chat_list)
            await db.commit()

        # Store message in DB
        new_message = ChatMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            chat_list_id=chat_list.id,
            message=message_text,
            status=MessageStatus.SENT,
        )
        db.add(new_message)
        await db.commit()

        # Update last message time
        chat_list.last_message_time = datetime.now(timezone.utc)
        await db.commit()

        isOnline = False
        # Send message to receiver if online
        if receiver_id in self.active_connections:
            isOnline = True
            await self.active_connections[receiver_id].send_json(
                {
                    "event_type": "NEW_MESSAGE",
                    "chat_list_id": chat_list.id,
                    "id": new_message.id,
                    "message": message_text,
                    "created_at": new_message.created_at,
                }
            )

        return isOnline

    async def get_chat_history(self, user_id: str, receiver_id: str, db: AsyncSession):
        """Fetch chat history between two users."""
        chat_list = await db.execute(
            select(ChatList).where(
                ((ChatList.user1_id == user_id) & (ChatList.user2_id == receiver_id))
                | ((ChatList.user1_id == receiver_id) & (ChatList.user2_id == user_id))
            )
        )
        chat_list = chat_list.scalar_one_or_none()

        if not chat_list:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = await db.execute(
            select(ChatMessage).where(ChatMessage.chat_list_id == chat_list.id)
        )
        messages = messages.scalars().all()
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

    async def is_user_online(self, user_id: str):
        """Check if user is online."""
        return user_id in self.active_connections

    async def get_user_chat_list(self, user_id: str, db: AsyncSession):
        """Get all chat lists for a user."""
        chat_lists = await db.execute(
            select(ChatList).where(
                (ChatList.user1_id == user_id) | (ChatList.user2_id == user_id)
            )
        )
        chat_lists = chat_lists.scalars().all()
        return chat_lists


chat_service = ChatService()
