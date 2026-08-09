
import imageio_ffmpeg
import subprocess
import os

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def run(cmd):
    # Fix paths for subprocess
    full_cmd = [FFMPEG] + cmd
    subprocess.run(full_cmd, capture_output=True, check=True)

# Final concat list
# ... (same logic as before, just replace subprocess call with full path)
