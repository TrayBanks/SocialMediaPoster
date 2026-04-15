#!/usr/bin/env python3
"""
SocialMediaPoster — Video upload automation for YouTube and TikTok.

Usage examples
--------------
Upload immediately to both platforms using CLI flags:
    python main.py upload \\
        --video clip.mp4 \\
        --platforms youtube tiktok \\
        --title "My Video" \\
        --description "Check this out!" \\
        --tags tech tutorial \\
        --category 28 \\
        --thumbnail thumb.jpg \\
        --privacy public

Upload with a metadata file (YAML or JSON), overriding title via CLI:
    python main.py upload \\
        --video clip.mp4 \\
        --platforms youtube \\
        --metadata-file meta.yaml \\
        --title "Override Title"

Schedule a post:
    python main.py upload \\
        --video clip.mp4 \\
        --platforms youtube tiktok \\
        --title "Scheduled Video" \\
        --schedule "2026-04-10 14:30 UTC"

Re-run OAuth authorization for a platform:
    python main.py auth --platform youtube
    python main.py auth --platform tiktok
"""

import argparse
import sys

from config.config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI,
    TIKTOK_TOKEN_PATH,
    YOUTUBE_CLIENT_SECRETS_PATH,
    YOUTUBE_TOKEN_PATH,
    ensure_token_dir,
    validate_tiktok_config,
    validate_youtube_config,
)
from utils.logger import logger


# ── Argument parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socialposter",
        description="Automate video uploads to YouTube and TikTok.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── upload subcommand ──────────────────────────────────────────────────────
    upload_p = subparsers.add_parser(
        "upload",
        help="Upload a video to one or more platforms.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    upload_p.add_argument(
        "--video",
        required=True,
        metavar="PATH",
        help="Path to the video file to upload.",
    )
    upload_p.add_argument(
        "--platforms",
        nargs="+",
        choices=["youtube", "tiktok"],
        required=True,
        metavar="PLATFORM",
        help="One or more platforms: youtube, tiktok.",
    )
    upload_p.add_argument(
        "--metadata-file",
        metavar="PATH",
        help="Path to a YAML or JSON file containing video metadata. "
             "CLI flags override values from this file.",
    )

    # Metadata flags (all optional when --metadata-file is used)
    upload_p.add_argument("--title", metavar="TEXT", help="Video title.")
    upload_p.add_argument(
        "--description", metavar="TEXT", help="Video description."
    )
    upload_p.add_argument(
        "--tags",
        nargs="+",
        metavar="TAG",
        help="Space-separated tags/keywords. "
             "On TikTok these are appended as #hashtags.",
    )
    upload_p.add_argument(
        "--category",
        metavar="ID",
        help="YouTube category ID (e.g. 22=People&Blogs, 28=Science&Tech). "
             "Ignored for TikTok.",
    )
    upload_p.add_argument(
        "--thumbnail",
        metavar="PATH",
        help="Path to a thumbnail image. "
             "YouTube: sets the video thumbnail. "
             "TikTok: not supported via API; a warning is shown.",
    )
    upload_p.add_argument(
        "--privacy",
        choices=["public", "private", "unlisted"],
        default="public",
        help="Visibility of the video.",
    )
    upload_p.add_argument(
        "--schedule",
        metavar="DATETIME",
        help='Publish at a future date/time instead of immediately. '
             'Examples: "2026-04-10 14:30 UTC", "2026-04-10T14:30:00+05:30", '
             '"2026-04-10 14:30 PST". '
             'TikTok constraint: 10 minutes – 20 days from now.',
    )
    upload_p.add_argument(
        "--tiktok-cover-ms",
        type=int,
        default=0,
        metavar="MS",
        help="TikTok only — millisecond offset of the video frame to use as cover. "
             "Default: 0 (first frame).",
    )

    # ── auth subcommand ────────────────────────────────────────────────────────
    auth_p = subparsers.add_parser(
        "auth",
        help="Authorize with a platform (re-runs the OAuth flow).",
    )
    auth_p.add_argument(
        "--platform",
        choices=["youtube", "tiktok"],
        required=True,
        help="Platform to authorize.",
    )

    return parser


# ── Command handlers ───────────────────────────────────────────────────────────

def cmd_auth(args) -> None:
    ensure_token_dir()

    if args.platform == "youtube":
        validate_youtube_config()
        from auth.youtube_auth import YouTubeAuthManager
        mgr = YouTubeAuthManager(YOUTUBE_TOKEN_PATH, YOUTUBE_CLIENT_SECRETS_PATH)
        mgr.force_reauth()
        logger.info("YouTube authorization complete.")

    elif args.platform == "tiktok":
        validate_tiktok_config()
        from auth.tiktok_auth import TikTokAuthManager
        mgr = TikTokAuthManager(
            TIKTOK_TOKEN_PATH,
            TIKTOK_CLIENT_KEY,
            TIKTOK_CLIENT_SECRET,
            TIKTOK_REDIRECT_URI,
        )
        mgr.force_reauth()
        logger.info("TikTok authorization complete.")


def cmd_upload(args) -> None:
    from metadata.parser import (
        merge_metadata,
        parse_cli_metadata,
        parse_metadata_file,
        parse_schedule,
    )
    from utils.file_utils import (
        find_metadata_file,
        find_thumbnail_file,
        validate_thumbnail_file,
        validate_video_file,
    )

    # ── Validate video file ────────────────────────────────────────────────────
    validate_video_file(args.video)

    # ── Auto-detect metadata file if not explicitly provided ──────────────────
    metadata_file = args.metadata_file
    if not metadata_file:
        metadata_file = find_metadata_file(args.video)
        if metadata_file:
            logger.info(f"Auto-detected metadata file: '{metadata_file}'")

    # ── Build metadata ─────────────────────────────────────────────────────────
    cli_meta = parse_cli_metadata(args)

    if metadata_file:
        file_meta = parse_metadata_file(metadata_file)
        metadata = merge_metadata(file_meta, cli_meta)
    else:
        metadata = cli_meta

    if not metadata.title:
        logger.error(
            "No title found. Add --title, or put a meta.yaml/meta.json "
            "file next to your video."
        )
        sys.exit(1)

    # ── Auto-detect thumbnail if not explicitly provided ──────────────────────
    if not metadata.thumbnail_path:
        auto_thumb = find_thumbnail_file(args.video)
        if auto_thumb:
            metadata.thumbnail_path = auto_thumb
            logger.info(f"Auto-detected thumbnail: '{auto_thumb}'")

    if metadata.thumbnail_path:
        validate_thumbnail_file(metadata.thumbnail_path)

    # ── Build schedule options ─────────────────────────────────────────────────
    schedule = parse_schedule(args)

    # ── Upload to each platform ────────────────────────────────────────────────
    ensure_token_dir()
    platforms = args.platforms
    results: dict[str, str] = {}

    for platform in platforms:
        try:
            if platform == "youtube":
                video_id = _upload_youtube(args, metadata, schedule)
                results["youtube"] = video_id

            elif platform == "tiktok":
                # Pass tiktok_cover_ms down into the uploader via metadata override
                video_id = _upload_tiktok(args, metadata, schedule)
                results["tiktok"] = video_id

        except Exception as exc:
            logger.error(f"Upload to {platform} failed: {exc}")
            sys.exit(1)

    logger.info("All uploads complete.")
    for platform, vid_id in results.items():
        logger.info(f"  {platform}: {vid_id}")


def _upload_youtube(args, metadata, schedule) -> str:
    validate_youtube_config()
    from auth.youtube_auth import YouTubeAuthManager
    from uploaders.youtube_uploader import YouTubeUploader

    auth = YouTubeAuthManager(YOUTUBE_TOKEN_PATH, YOUTUBE_CLIENT_SECRETS_PATH)
    uploader = YouTubeUploader(auth)
    return uploader.upload(args.video, metadata, schedule)


def _upload_tiktok(args, metadata, schedule) -> str:
    validate_tiktok_config()
    from auth.tiktok_auth import TikTokAuthManager
    from uploaders.tiktok_uploader import TikTokUploader

    auth = TikTokAuthManager(
        TIKTOK_TOKEN_PATH,
        TIKTOK_CLIENT_KEY,
        TIKTOK_CLIENT_SECRET,
        TIKTOK_REDIRECT_URI,
    )
    uploader = TikTokUploader(auth)

    # Inject tiktok_cover_ms into the upload if provided
    if hasattr(args, "tiktok_cover_ms") and args.tiktok_cover_ms:
        uploader._cover_ms = args.tiktok_cover_ms

    return uploader.upload(args.video, metadata, schedule)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "upload":
            cmd_upload(args)
        elif args.command == "auth":
            cmd_auth(args)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
