import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from metadata.models import ScheduleOptions, VideoMetadata


# ── File-based metadata ────────────────────────────────────────────────────────

def parse_metadata_file(path: str) -> VideoMetadata:
    """
    Load VideoMetadata from a JSON or YAML file.

    JSON example:
        {
            "title": "My Video",
            "description": "Check this out!",
            "tags": ["tech", "tutorial"],
            "category_id": "28",
            "thumbnail_path": "thumb.jpg",
            "privacy": "public"
        }

    YAML example:
        title: My Video
        description: Check this out!
        tags:
          - tech
          - tutorial
        category_id: "28"
        thumbnail_path: thumb.jpg
        privacy: public
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Metadata file not found: '{path}'")

    suffix = p.suffix.lower()
    with open(p, "r", encoding="utf-8") as fh:
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(fh) or {}
        elif suffix == ".json":
            data = json.load(fh)
        else:
            raise ValueError(
                f"Unsupported metadata file format '{suffix}'. Use .json, .yaml, or .yml"
            )

    return VideoMetadata(
        title=data.get("title", ""),
        description=data.get("description", ""),
        tags=data.get("tags", []),
        category_id=str(data.get("category_id", "22")),
        thumbnail_path=data.get("thumbnail_path") or None,
        privacy=data.get("privacy", "public"),
    )


# ── CLI-based metadata ─────────────────────────────────────────────────────────

def parse_cli_metadata(args) -> VideoMetadata:
    """Build a VideoMetadata from argparse Namespace (upload subcommand)."""
    return VideoMetadata(
        title=args.title or "",
        description=args.description or "",
        tags=args.tags or [],
        category_id=str(args.category) if args.category else "22",
        thumbnail_path=args.thumbnail or None,
        privacy=args.privacy or "public",
    )


def merge_metadata(file_meta: VideoMetadata, cli_meta: VideoMetadata) -> VideoMetadata:
    """
    Merge two VideoMetadata objects.  CLI values take precedence over file values,
    but only when the CLI value is non-empty / non-default.
    """
    return VideoMetadata(
        title=cli_meta.title or file_meta.title,
        description=cli_meta.description or file_meta.description,
        tags=cli_meta.tags if cli_meta.tags else file_meta.tags,
        category_id=cli_meta.category_id if cli_meta.category_id != "22" else file_meta.category_id,
        thumbnail_path=cli_meta.thumbnail_path or file_meta.thumbnail_path,
        privacy=cli_meta.privacy if cli_meta.privacy != "public" else file_meta.privacy,
    )


# ── Schedule parsing ───────────────────────────────────────────────────────────

_FORMATS = [
    "%Y-%m-%d %H:%M %Z",   # "2026-04-10 14:30 UTC"
    "%Y-%m-%d %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with offset
    "%Y-%m-%dT%H:%M%z",
    "%Y-%m-%d %H:%M",       # naive → treated as UTC
    "%Y-%m-%d %H:%M:%S",
]

_TZ_ALIASES = {
    "UTC": "UTC",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "GMT": "UTC",
    "BST": "Europe/London",
    "CET": "Europe/Paris",
    "IST": "Asia/Kolkata",
    "JST": "Asia/Tokyo",
    "AEST": "Australia/Sydney",
}


def _parse_datetime_string(value: str) -> datetime:
    """Parse a human-friendly datetime string into a timezone-aware datetime."""
    value = value.strip()

    # Try ISO 8601 first (already has tz offset like +05:30 or Z)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    # Try stripping a trailing timezone abbreviation
    parts = value.rsplit(" ", 1)
    tz_name = None
    if len(parts) == 2 and parts[1].upper() in _TZ_ALIASES:
        tz_name = _TZ_ALIASES[parts[1].upper()]
        value_without_tz = parts[0]
    else:
        value_without_tz = value

    # Try each format on the string without the tz suffix
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(value_without_tz, fmt)
            if tz_name:
                try:
                    dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                except ZoneInfoNotFoundError:
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    raise ValueError(
        f"Cannot parse schedule datetime: '{value}'\n"
        "Expected formats: '2026-04-10 14:30 UTC', '2026-04-10T14:30:00+05:30', "
        "'2026-04-10 14:30 PST', etc."
    )


def parse_schedule(args) -> ScheduleOptions:
    """Build ScheduleOptions from argparse Namespace."""
    if not getattr(args, "schedule", None):
        return ScheduleOptions(enabled=False, publish_at=None)

    dt = _parse_datetime_string(args.schedule)
    now = datetime.now(tz=timezone.utc)

    if dt <= now:
        raise ValueError(
            f"Scheduled time '{args.schedule}' is in the past. "
            "Please provide a future date and time."
        )

    return ScheduleOptions(enabled=True, publish_at=dt)
