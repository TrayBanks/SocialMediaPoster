import math
import time

import requests
from tqdm import tqdm

from auth.tiktok_auth import TikTokAuthManager
from metadata.models import ScheduleOptions, VideoMetadata
from uploaders.base_uploader import BaseUploader
from utils.file_utils import get_file_size, get_mime_type
from utils.logger import logger

TIKTOK_API_BASE = "https://open.tiktokapis.com"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_RETRIES = 3
POLL_INTERVAL = 5   # seconds between status polls
POLL_TIMEOUT = 300  # max seconds to wait for publish completion

# TikTok scheduling: 10 min minimum, 20 days maximum in the future
SCHEDULE_MIN_OFFSET = 600          # 10 minutes
SCHEDULE_MAX_OFFSET = 20 * 86400   # 20 days


class TikTokUploader(BaseUploader):
    """
    Uploads videos to TikTok using the Content Posting API v2.

    Features:
    - Chunked file upload (10 MB chunks) with a tqdm progress bar.
    - Per-chunk retry logic (up to 3 retries with exponential back-off).
    - Scheduled publishing via scheduled_publish_time (Unix timestamp).
    - Privacy level is automatically set to SELF_ONLY when scheduling.
    - Hashtags from metadata.tags are appended to the video title/description.
    """

    def __init__(self, auth: TikTokAuthManager) -> None:
        self._auth = auth

    # ── Public API ─────────────────────────────────────────────────────────────

    def upload(
        self,
        video_path: str,
        metadata: VideoMetadata,
        schedule: ScheduleOptions,
    ) -> str:
        if metadata.thumbnail_path:
            logger.warning(
                "TikTok does not support custom image thumbnails via the v2 API. "
                "The cover frame is determined by the video content. "
                "Use --tiktok-cover-ms to specify a frame offset (milliseconds)."
            )

        file_size = get_file_size(video_path)
        total_chunks = math.ceil(file_size / CHUNK_SIZE)

        # Build the description with hashtags appended
        description = self._build_description(metadata)

        logger.info(
            f"Initializing TikTok upload: '{metadata.title}' "
            f"({file_size / 1024 / 1024:.1f} MB, {total_chunks} chunk(s))"
        )

        init_response = self._init_upload(
            metadata, description, schedule, file_size, total_chunks
        )

        upload_url = init_response["data"]["upload_url"]
        publish_id = init_response["data"]["publish_id"]

        logger.info(f"TikTok publish ID: {publish_id}")

        self._upload_chunks(upload_url, video_path, file_size, total_chunks)

        if not schedule.enabled:
            # For direct posts, poll for completion
            status = self._poll_publish_status(publish_id)
            logger.info(f"TikTok upload complete. Status: {status}")
        else:
            logger.info(
                f"TikTok video scheduled for: {schedule.publish_at.isoformat()}"
            )

        return publish_id

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> None:
        """
        TikTok v2 API does not support post-upload thumbnail images.
        This method is a no-op; a warning is already emitted during upload().
        """
        pass

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_headers(self) -> dict:
        access_token = self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _build_description(self, metadata: VideoMetadata) -> str:
        """Append hashtags from tags list to the description."""
        parts = [metadata.description] if metadata.description else []
        for tag in metadata.tags:
            hashtag = tag if tag.startswith("#") else f"#{tag}"
            parts.append(hashtag)
        return " ".join(parts).strip()

    def _init_upload(
        self,
        metadata: VideoMetadata,
        description: str,
        schedule: ScheduleOptions,
        file_size: int,
        total_chunks: int,
    ) -> dict:
        if schedule.enabled and schedule.publish_at:
            scheduled_ts = int(schedule.publish_at.timestamp())
            now = int(time.time())
            offset = scheduled_ts - now

            if offset < SCHEDULE_MIN_OFFSET:
                raise ValueError(
                    f"TikTok requires a scheduled time at least 10 minutes in the future. "
                    f"Provided offset: {offset}s"
                )
            if offset > SCHEDULE_MAX_OFFSET:
                raise ValueError(
                    f"TikTok requires a scheduled time no more than 20 days in the future. "
                    f"Provided offset: {offset / 86400:.1f} days"
                )
            privacy_level = "SELF_ONLY"  # required by TikTok when scheduling
        else:
            scheduled_ts = None
            privacy_level = self._map_privacy(metadata.privacy)

        # TikTok title max is 150 characters
        title = metadata.title[:150] if metadata.title else description[:150]

        post_info: dict = {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 0,
        }
        if scheduled_ts:
            post_info["scheduled_publish_time"] = scheduled_ts

        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": total_chunks,
        }

        payload = {"post_info": post_info, "source_info": source_info}

        resp = requests.post(
            f"{TIKTOK_API_BASE}/v2/post/publish/video/init/",
            json=payload,
            headers=self._get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("error", {}).get("code", "ok") != "ok":
            err = data["error"]
            raise RuntimeError(
                f"TikTok init failed [{err.get('code')}]: {err.get('message')}"
            )

        return data

    def _upload_chunks(
        self,
        upload_url: str,
        video_path: str,
        file_size: int,
        total_chunks: int,
    ) -> None:
        with open(video_path, "rb") as fh, tqdm(
            total=file_size,
            unit="B",
            unit_scale=True,
            desc="Uploading to TikTok",
            ncols=80,
        ) as pbar:
            for chunk_index in range(total_chunks):
                start = chunk_index * CHUNK_SIZE
                end = min(start + CHUNK_SIZE, file_size) - 1
                fh.seek(start)
                chunk_data = fh.read(end - start + 1)

                self._upload_single_chunk(
                    upload_url, chunk_data, chunk_index, start, end, file_size
                )
                pbar.update(len(chunk_data))

    def _upload_single_chunk(
        self,
        upload_url: str,
        chunk_data: bytes,
        chunk_index: int,
        start: int,
        end: int,
        file_size: int,
    ) -> None:
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Type": get_mime_type(upload_url) or "video/mp4",
        }

        for attempt in range(1, CHUNK_RETRIES + 1):
            try:
                resp = requests.put(
                    upload_url,
                    data=chunk_data,
                    headers=headers,
                    timeout=120,
                )
                if resp.status_code in (200, 201, 206):
                    return
                raise RuntimeError(
                    f"Unexpected status {resp.status_code} for chunk {chunk_index}: "
                    f"{resp.text[:200]}"
                )
            except Exception as exc:
                if attempt == CHUNK_RETRIES:
                    raise RuntimeError(
                        f"Chunk {chunk_index} failed after {CHUNK_RETRIES} attempts: {exc}"
                    ) from exc
                wait = 2 ** attempt
                logger.warning(
                    f"Chunk {chunk_index} attempt {attempt}/{CHUNK_RETRIES} failed "
                    f"({exc}), retrying in {wait}s…"
                )
                time.sleep(wait)

    def _poll_publish_status(self, publish_id: str) -> str:
        """Poll the publish status endpoint until complete or timeout."""
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            resp = requests.post(
                f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/",
                json={"publish_id": publish_id},
                headers=self._get_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("error", {}).get("code", "ok") != "ok":
                err = data["error"]
                raise RuntimeError(
                    f"TikTok status fetch failed [{err.get('code')}]: {err.get('message')}"
                )

            status = data.get("data", {}).get("status", "")
            if status == "PUBLISH_COMPLETE":
                return status
            if status in ("FAILED", "PUBLISH_FAILED"):
                fail_reason = data.get("data", {}).get("fail_reason", "unknown")
                raise RuntimeError(f"TikTok publish failed: {fail_reason}")

            logger.info(f"TikTok publish status: {status} — waiting…")
            time.sleep(POLL_INTERVAL)

        raise TimeoutError(
            f"TikTok publish did not complete within {POLL_TIMEOUT}s "
            f"(publish_id: {publish_id})."
        )

    @staticmethod
    def _map_privacy(privacy: str) -> str:
        """Map generic privacy strings to TikTok privacy level constants."""
        mapping = {
            "public": "PUBLIC_TO_EVERYONE",
            "private": "SELF_ONLY",
            "unlisted": "MUTUAL_FOLLOW_FRIENDS",
        }
        return mapping.get(privacy.lower(), "PUBLIC_TO_EVERYONE")
