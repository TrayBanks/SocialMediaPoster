from abc import ABC, abstractmethod

from metadata.models import ScheduleOptions, VideoMetadata


class BaseUploader(ABC):
    """Abstract base class that every platform uploader must implement."""

    @abstractmethod
    def upload(
        self,
        video_path: str,
        metadata: VideoMetadata,
        schedule: ScheduleOptions,
    ) -> str:
        """
        Upload a video with the given metadata.

        Parameters
        ----------
        video_path : str
            Absolute or relative path to the local video file.
        metadata : VideoMetadata
            Title, description, tags, category, thumbnail path, and privacy level.
        schedule : ScheduleOptions
            Whether to post immediately or schedule for a future datetime.

        Returns
        -------
        str
            The platform-specific video/post ID of the uploaded content.
        """

    @abstractmethod
    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> None:
        """
        Set or update the thumbnail for an already-uploaded video.

        Parameters
        ----------
        video_id : str
            The platform-specific video ID returned by :meth:`upload`.
        thumbnail_path : str
            Path to the thumbnail image file.
        """
