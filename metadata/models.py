from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VideoMetadata:
    title: str = ""
    description: str = ""
    # YouTube: used as keyword tags. TikTok: appended as #hashtags in the description.
    tags: list = field(default_factory=list)
    # YouTube category ID (e.g. "22" = People & Blogs, "28" = Science & Technology).
    # Ignored for TikTok — the platform does not expose a category field in its v2 API.
    category_id: str = "22"
    thumbnail_path: str | None = None
    # "public" | "private" | "unlisted"
    privacy: str = "public"


@dataclass
class ScheduleOptions:
    enabled: bool = False
    # Must be a timezone-aware datetime when enabled is True.
    publish_at: datetime | None = None
