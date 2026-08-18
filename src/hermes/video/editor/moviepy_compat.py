"""Small compatibility layer for MoviePy 1.x and 2.x imports."""

try:
    from moviepy.editor import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    import moviepy.video.fx.all as _legacy_vfx

    vfx = _legacy_vfx
except ModuleNotFoundError:
    from moviepy import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    from moviepy.video.fx import Crop

    class _VfxCompat:
        @staticmethod
        def crop(clip, **kwargs):
            return clip.with_effects([Crop(**kwargs)])

    vfx = _VfxCompat()

__all__ = [
    "AudioFileClip",
    "CompositeVideoClip",
    "ImageClip",
    "VideoFileClip",
    "concatenate_videoclips",
    "vfx",
]
