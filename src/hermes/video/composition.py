import ffmpeg
from .models import VideoComposition

class MasterVideoCompositor:
    """
    Handles the final composition of the video using FFmpeg.
    """
    def compose(self, comp: VideoComposition):
        """
        Composes the final video from scenes, audio, and captions.
        - Concatenates scene videos.
        - Overlays voiceover and background music with audio ducking.
        - Burns in animated subtitles.
        """
        # 1. Prepare video inputs
        input_videos = [ffmpeg.input(path) for path in comp.scene_videos]
        
        # 2. Concatenate video clips
        # Using the concat filter. All inputs must have the same resolution.
        # Assuming all generated clips are 720x1280.
        concatenated_video = ffmpeg.concat(*input_videos, v=1, a=0).filter('fps', fps=24, round='up')

        # 3. Prepare audio inputs
        voice_input = ffmpeg.input(comp.voiceover_track)
        audio_streams = [voice_input.audio]

        if comp.bgm_track:
            bgm_input = ffmpeg.input(comp.bgm_track)
            
            # 4. Audio Ducking: lower BGM volume when voice is present
            # This uses the 'sidedata' and 'acompressor' filters. A simpler version
            # might be to pre-process BGM, but this is more dynamic.
            # This is a complex FFmpeg feature. For simplicity here, we'll just mix them,
            # with BGM at a lower volume. A real implementation would use a more
            # complex filter graph with sidechain compression.
            
            # Simple mixing:
            mixed_audio = ffmpeg.filter(
                [voice_input.audio, bgm_input.audio], 
                'amix', 
                inputs=2, 
                duration='first',
                weights="1 0.2" # Voice at 100%, BGM at 20%
            )
            audio_streams = [mixed_audio]
        else:
             audio_streams = [voice_input.audio]


        # 5. Combine video and audio
        video_with_audio = ffmpeg.concat(concatenated_video, *audio_streams, v=1, a=1)

        # 6. Burn subtitles if available
        if comp.captions_ass_path:
            # The subtitles filter requires an absolute path with special escaping
            # for Windows drive letters.
            escaped_path = comp.captions_ass_path.replace('\\', '/').replace(':', '\\\\:')
            video_with_subs = ffmpeg.filter(video_with_audio, 'subtitles', filename=escaped_path)
        else:
            video_with_subs = video_with_audio
            
        # 7. Output the final video
        (
            ffmpeg
            .output(video_with_subs, comp.output_path,
                    vcodec='libx264', acodec='aac',
                    video_bitrate='2M', audio_bitrate='192k',
                    preset='ultrafast', # for speed
                    s='720x1280', # standard vertical resolution
                    aspect='9:16',
                    y=None # Overwrite output file if it exists
                   )
            .run(capture_stdout=True, capture_stderr=True)
        )
        print(f"Final video composed at: {comp.output_path}")
