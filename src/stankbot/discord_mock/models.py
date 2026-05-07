"""Mock Discord objects for dev mode — no Gateway, no real Discord API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class MockSticker:
    id: int
    name: str


@dataclass
class MockPartialEmoji:
    id: int | None = None
    name: str | None = None
    animated: bool = False


@dataclass
class MockMember:
    id: int
    name: str
    display_name: str
    avatar: str | None = None
    bot: bool = False
    guild_permissions: int = 0


@dataclass
class MockTextChannel:
    id: int
    name: str
    guild: MockGuild

    async def send(self, *, embed=None, content=None):
        """No-op in mock mode."""
        pass


@dataclass
class MockGuild:
    id: int
    name: str
    icon: str | None = None
    members: dict[int, MockMember] = field(default_factory=dict)
    channels: dict[int, MockTextChannel] = field(default_factory=dict)
    emojis: list = field(default_factory=list)

    def get_member(self, user_id: int) -> MockMember | None:
        return self.members.get(user_id)

    def get_emoji(self, emoji_id: int):
        for e in self.emojis:
            if getattr(e, "id", None) == emoji_id:
                return e
        return None

    def get_role(self, role_id: int):
        return None


@dataclass
class MockRole:
    id: int
    name: str


@dataclass
class MockMessage:
    id: int
    guild: MockGuild
    channel: MockTextChannel
    author: MockMember
    content: str = ""
    stickers: list[MockSticker] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    async def add_reaction(self, emoji):
        """No-op in mock mode."""
        pass


@dataclass
class MockReactionPayload:
    guild_id: int
    channel_id: int
    message_id: int
    user_id: int
    emoji: MockPartialEmoji
    member: MockMember | None = None
