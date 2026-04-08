import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tqdm import tqdm

from auth.youtube_auth import YouTubeAuthManager
from metadata.models import ScheduleOptions, VideoMetadata
from uploaders.base_uploader import BaseUploader
from utils.logger import logger

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}


class YouTubeUploader(BaseUploader):
    """
    Uploads videos to YouTube using the Data API v3.

    Features:
    - Resumable (chunked) upload with a tqdm progress bar.
    - Automatic retry with exponential back-off on transient HTTP errors.
    - Scheduled publishing via status.publishAt (video stays private until then).
    - Thumbnail upload via the thumbnails.set() API.
    """

    def __init__(self, auth: YouTubeAuthManager) -> None:
        self._auth = auth
        self._service = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def upload(
        self,
        video_path: str,
        metadata: VideoMetadata,
        schedule: ScheduleOptions,
    ) -> str:
        service = self._get_service()
        body = self._build_video_body(metadata, schedule)

        media = MediaFileUpload(
            video_path,
            mimetype="video/*",
            chunksize=CHUNK_SIZE,
            resumable=True,
        )

        request = service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        logger.info(f"Starting YouTube upload: '{metadata.title}'")
        video_id = self._execute_resumable_upload(request, video_path)

        logger.info(f"YouTube upload complete. Video ID: {video_id}")

        if metadata.thumbnail_path:
            self.set_thumbnail(video_id, metadata.thumbnail_path)

        if schedule.enabled:
            logger.info(
                f"Video scheduled to publish at: {schedule.publish_at.isoformat()}"
            )
        else:
            logger.info(
                f"Video URL: https://www.youtube.com/watch?v={video_id}"
            )

        return video_id

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> None:
        service = self._get_service()
        media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg", resumable=False)
        try:
            service.thumbnails().set(
                videoId=video_id, media_body=media
            ).execute()
            logger.info(f"Thumbnail set for video {video_id}.")
        except HttpError as exc:
            logger.warning(f"Could not set YouTube thumbnail: {exc}")

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_service(self):
        if self._service is None:
            creds = self._auth.get_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def _build_video_body(
        self, metadata: VideoMetadata, schedule: ScheduleOptions
    ) -> dict:
        snippet = {
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "categoryId": metadata.category_id,
        }

        if schedule.enabled and schedule.publish_at:
            # Scheduled: video must be private; publishAt triggers auto-publish
            status = {
                "privacyStatus": "private",
                "publishAt": schedule.publish_at.isoformat(),
                "selfDeclaredMadeForKids": False,
            }
        else:
            status = {
                "privacyStatus": metadata.privacy,
                "selfDeclaredMadeForKids": False,
            }

        return {"snippet": snippet, "status": status}

    def _execute_resumable_upload(self, request, video_path: str) -> str:
        """Drive the resumable upload loop, retrying on transient errors."""
        from utils.file_utils import get_file_size

        file_size = get_file_size(video_path)
        response = None
        error = None
        retry_count = 0

        with tqdm(
            total=file_size,
            unit="B",
            unit_scale=True,
            desc="Uploading to YouTube",
            ncols=80,
        ) as pbar:
            while response is None:
                try:
                    status, response = request.next_chunk()
                    if status:
                        uploaded = int(status.resumable_progress)
                        pbar.update(uploaded - pbar.n)
                    if response is not None:
                        pbar.update(file_size - pbar.n)
                except HttpError as exc:
                    if exc.resp.status in RETRIABLE_STATUS_CODES:
                        error = exc
                    else:
                        raise
                except Exception as exc:
                    error = exc

                if error:
                    retry_count += 1
                    if retry_count > MAX_RETRIES:
                        raise RuntimeError(
                            f"YouTube upload failed after {MAX_RETRIES} retries: {error}"
                        )
                    wait = 2 ** retry_count
                    logger.warning(
                        f"Upload error (attempt {retry_count}/{MAX_RETRIES}), "
                        f"retrying in {wait}s: {error}"
                    )
                    time.sleep(wait)
                    error = None

        return response["id"]
