"""ASS subtitle file generator for TikTok-style animated captions."""
from __future__ import annotations

from pathlib import Path

from hermes.video.models import AnimatedCaptionSegment, AnimatedCaptionWord


def _fmt_ts(seconds: float) -> str:
    """Format seconds to ASS timestamp H:MM:SS.CC (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def generate_ass(
    segments: list[AnimatedCaptionSegment],
    output_path: str,
    width: int = 720,
    height: int = 1280,
) -> str:
    """Generate a .ass subtitle file with TikTok-style animated captions.

    Features: yellow text (#FFFF00), size 48, centered bottom, black outline,
    per-word \\fad(200,200) fade-in/out.

    Returns output_path.
    """
    play_res_x = width
    play_res_y = height

    # MarginL, MarginR, MarginV — center bottom, large margins keep text off edges
    margin_v = height // 8

    style_line = (
        f"Default,Arial Black,48,&H0000FFFF,&H000000FF,"
        f"&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,"
        f"2,2,2,{margin_v},0,0,0,1"
    )

    lines = [
        "[Script Info]",
        "Title:Hermes Video Captions",
        "ScriptType:v4.00+",
        f"PlayResX:{play_res_x}",
        f"PlayResY:{play_res_y}",
        "WrapStyle:0",
        "ScaledBorderAndShadow:yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    for segment in segments:
        for word in segment.words:
            start = _fmt_ts(word.start)
            end = _fmt_ts(word.end)
            # Per-word line with fade-in(200ms) and fade-out(200ms)
            text = f"{{\\fad(200,200)}}{word.word}"
            lines.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"
            )

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return str(p)


def generate_ass_from_text(
    text: str,
    audio_duration: float,
    output_path: str,
    width: int = 720,
    height: int = 1280,
) -> str:
    """Split plain text into words with proportional timing, then generate .ass.

    Assumes uniform word duration spread across audio_duration.
    """
    words_raw = text.split()
    if not words_raw:
        # Empty captions file
        return generate_ass([], output_path, width, height)

    duration_per_word = audio_duration / len(words_raw)
    words = [
        AnimatedCaptionWord(
            word=w,
            start=round(i * duration_per_word, 3),
            end=round((i + 1) * duration_per_word, 3),
        )
        for i, w in enumerate(words_raw)
    ]
    segment = AnimatedCaptionSegment(text=text, words=words)
    return generate_ass([segment], output_path, width, height)
