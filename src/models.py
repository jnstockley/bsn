from datetime import datetime
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
        return f"YoutubeChannel(id={self.id}, name={self.name}, num_videos={self.num_videos})"


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
        return f"YoutubeVideo(id={self.id}, title={self.title}, url={self.url}, uploaded_at={self.uploaded_at})"


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
