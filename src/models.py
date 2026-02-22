from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class YoutubeChannel(Base):
    __tablename__ = "youtube_channel"

    id: Mapped[str] = mapped_column(primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    num_videos: Mapped[int] = mapped_column(nullable=False)
    video: Mapped["YoutubeVideo"] = relationship(back_populates="youtube_channel")

    def __repr__(self):
        return f"YoutubeChannel(name={self.name}, num_videos={self.num_videos})"


class YoutubeVideo(Base):
    __tablename__ = "youtube_video"

    id: Mapped[str] = mapped_column(primary_key=True, nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(nullable=False)
    is_short: Mapped[bool] = mapped_column(nullable=False)
    is_livestream: Mapped[bool] = mapped_column(nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(nullable=False)
    youtube_channel_id = mapped_column(ForeignKey("youtube_channel.id"))

    youtube_channel: Mapped["YoutubeChannel"] = relationship(back_populates="video")

    def __repr__(self):
        return f"YoutubeVideo(title={self.title}, url={self.url}, uploaded_at={self.uploaded_at}, uploaded_by={self.youtube_channel.name})"


class OauthCredential(Base):
    __tablename__ = "oauth_credential"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    client_secret: Mapped[Optional[str]] = mapped_column(nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(nullable=True)
    token_uri: Mapped[Optional[str]] = mapped_column(nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(nullable=True)
    token_type: Mapped[Optional[str]] = mapped_column(nullable=True)
    expiry: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    extra: Mapped[Optional[str]] = mapped_column(nullable=True)

    def __repr__(self):
        return f"OauthCredential(id={self.id}, client_id={self.client_id}, user_email={self.user_email})"

class Service(Enum):
    YOUTUBE = "youtube"

class QuotaPolicy(Base):
    """Defines the quota limit/configuration for a service.

    - service: a short name for the service (e.g. 'youtube')
    - limit: maximum allowed requests in the configured window
    """

    __tablename__ = "quota_policy"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service: Mapped[Service] = mapped_column(nullable=False, unique=True)
    limit: Mapped[int] = mapped_column(nullable=False)

    usages: Mapped[list["QuotaUsage"]] = relationship(back_populates="config", cascade="all, delete-orphan")

    def __repr__(self):
        return f"QuotaPolicy(id={self.id}, service={self.service}, limit={self.limit})"


class QuotaUsage(Base):
    """Stores snapshots of quota usage tied to the singleton QuotaConfig.

    This model explicitly stores the window boundaries and a reset_at timestamp which should align
    with the QuotaConfig daily reset (computed in UTC by application logic).
    """

    __tablename__ = "quota_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_id = mapped_column(ForeignKey("quota_policy.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    window_start: Mapped[datetime] = mapped_column(nullable=False)
    window_end: Mapped[datetime] = mapped_column(nullable=False)
    usage_count: Mapped[int] = mapped_column(nullable=False)
    quota_remaining: Mapped[Optional[int]] = mapped_column(nullable=True)

    # reset_at should be the UTC datetime matching the config's next reset for the window
    reset_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    config: Mapped["QuotaPolicy"] = relationship(back_populates="usages")

    def __repr__(self):
        return (
            f"QuotaUsage(id={self.id}, config_id={self.config_id}, timestamp={self.timestamp}, "
            f"usage_count={self.usage_count}, quota_remaining={self.quota_remaining}, reset_at={self.reset_at})"
        )
