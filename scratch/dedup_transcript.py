import re
import sys

# Force stdout to UTF-8
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_clean_text(vtt_path):
    with open(vtt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    text_segments = []
    for line in lines:
        line = line.strip()
        # Skip VTT formatting lines
        if not line or "WEBVTT" in line or "Kind:" in line or "Language:" in line or "-->" in line or line.isdigit():
            continue
        # Clean HTML tags
        line = re.sub(r'<[^>]+>', '', line)
        line = line.strip()
        if line:
            text_segments.append(line)
            
    # Deduplicate rolling text
    # A rolling text segment often starts with words from the previous segment.
    # We can reconstruct the full text by merging consecutive segments with maximum overlap.
    if not text_segments:
        return ""
        
    merged_text = text_segments[0]
    
    for i in range(1, len(text_segments)):
        next_segment = text_segments[i]
        
        # Find the maximum overlap between the end of merged_text and the start of next_segment
        # We check word-level overlap
        merged_words = merged_text.split()
        next_words = next_segment.split()
        
        max_overlap = 0
        for overlap_len in range(1, min(len(merged_words), len(next_words)) + 1):
            suffix = merged_words[-overlap_len:]
            prefix = next_words[:overlap_len]
            if suffix == prefix:
                max_overlap = overlap_len
                
        if max_overlap > 0:
            # Append the non-overlapping part of next_segment
            remaining_words = next_words[max_overlap:]
            if remaining_words:
                merged_text += " " + " ".join(remaining_words)
        else:
            merged_text += " " + next_segment
            
    return merged_text

cleaned_text = get_clean_text('scratch/subtitles.vi.vtt')
print("Total words in cleaned transcript:", len(cleaned_text.split()))
print("\nFirst 1000 characters of cleaned transcript:")
print(cleaned_text[:1000] + "...")

# Save the clean transcript to a file
with open('scratch/clean_transcript.txt', 'w', encoding='utf-8') as f:
    f.write(cleaned_text)
