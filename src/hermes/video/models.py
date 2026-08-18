from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class CreativeBrief(BaseModel):
    """Initial creative direction for the video."""
    product_sku: str
    angle: Literal["Problem-Agitate-Solve", "Hook-Feature-Benefit", "Before-After"]
    target_audience: str
    key_hook: str
    cta: str # Call to Action

class Scene(BaseModel):
    """Represents a single scene in the video plan."""
    scene_number: int
    duration_seconds: float
    visual_prompt: str
    voiceover_script: str
    text_overlay: Optional[str] = None
    # Paths populated during pipeline execution
    keyframe_image_path: Optional[str] = None
    scene_video_path: Optional[str] = None
    voiceover_audio_path: Optional[str] = None

class ScenePlan(BaseModel):
    """The full plan for the video, composed of multiple scenes."""
    project_id: str
    brief: CreativeBrief
    scenes: List[Scene]
    bgm_path: Optional[str] = None
    final_video_path: Optional[str] = None

class AnimatedCaptionWord(BaseModel):
    """Timestamp for a single word in the caption."""
    word: str
    start: float # in seconds
    end: float # in seconds

class AnimatedCaptionSegment(BaseModel):
    """A full sentence or segment with word-level timestamps."""
    text: str
    words: List[AnimatedCaptionWord]

class VideoComposition:
    """A descriptor for the final video composition task."""
    project_id: str
    scene_videos: List[str] # List of final video paths for each scene
    voiceover_track: str # Path to the combined voiceover track
    bgm_track: Optional[str]
    captions_ass_path: Optional[str] # Path to the .ass subtitle file
    output_path: str
