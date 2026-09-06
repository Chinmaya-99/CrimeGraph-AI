from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Integer, Text, text
)
from sqlalchemy.dialects.postgresql import JSONB
from data_base.database import Base


class SocialMediaRecord(Base):
    __tablename__ = "social_media_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    social_media_record_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # USER / PLATFORM
    # ----------------------------------------------------------------
    platform = Column(String(50), nullable=False)
    user_id = Column(String(100), nullable=False)
    username = Column(String(100), nullable=True)

    # ----------------------------------------------------------------
    # POST
    # ----------------------------------------------------------------
    post_id = Column(String(100), nullable=True)
    post_content = Column(Text, nullable=True)
    post_timestamp = Column(TIMESTAMP, nullable=True)

    # ----------------------------------------------------------------
    # ENGAGEMENT
    # ----------------------------------------------------------------
    likes_count = Column(
        Integer,
        server_default=text("0"),
        nullable=True
    )
    comments_count = Column(
        Integer,
        server_default=text("0"),
        nullable=True
    )
    shares_count = Column(
        Integer,
        server_default=text("0"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # EXTRACTED DATA
    # ----------------------------------------------------------------
    mentioned_users = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    hashtags = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    phone_numbers = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    external_links = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # PROVENANCE
    # ----------------------------------------------------------------
    source_file = Column(String(500), nullable=True)
    source_hash = Column(String(64), nullable=True)

    created_at = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<SocialMediaRecord "
            f"social_media_record_id={self.social_media_record_id} "
            f"platform={self.platform!r} "
            f"username={self.username!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "social_media_record_id": self.social_media_record_id,
            "platform": self.platform,
            "user_id": self.user_id,
            "username": self.username,
            "post_id": self.post_id,
            "post_content": self.post_content,
            "post_timestamp": (
                str(self.post_timestamp)
                if self.post_timestamp else None
            ),
            "likes_count": self.likes_count,
            "comments_count": self.comments_count,
            "shares_count": self.shares_count,
            "mentioned_users": self.mentioned_users or [],
            "hashtags": self.hashtags or [],
            "phone_numbers": self.phone_numbers or [],
            "external_links": self.external_links or [],
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }