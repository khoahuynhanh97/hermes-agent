import re
import sys

# Force stdout to UTF-8
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_vtt(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove WebVTT header
    content = re.sub(r'^WEBVTT\s*\n.*?\n', '', content, flags=re.DOTALL)
    
    # Split into blocks
    blocks = content.split('\n\n')
    lines = []
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # Split block lines
        block_lines = block.split('\n')
        
        # Check if first line is timestamp
        if len(block_lines) >= 2 and '-->' in block_lines[0]:
            # The remaining lines are the text
            text = ' '.join(block_lines[1:])
            # Clean HTML-like tags (e.g. <c>...</c>)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text:
                lines.append(text)
        elif len(block_lines) >= 3 and '-->' in block_lines[1]:
            # Sometimes there is an ID line before the timestamp
            text = ' '.join(block_lines[2:])
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text:
                lines.append(text)
                
    # Deduplicate consecutive identical lines or overlap words
    cleaned_lines = []
    last_line = ""
    for line in lines:
        if line != last_line:
            cleaned_lines.append(line)
            last_line = line
            
    # Combine lines, but try to keep it readable. 
    # Since VTT segments are very short, we group them into larger paragraphs or sentences.
    text_content = " ".join(cleaned_lines)
    
    # Simple deduplication of rolling words (e.g. "hướng dẫn hướng dẫn các bạn")
    # Let's just output the cleaned lines first to inspect
    return cleaned_lines

cleaned = parse_vtt('scratch/subtitles.vi.vtt')
print("Total parsed lines:", len(cleaned))
print("\nFirst 30 lines:")
for i, line in enumerate(cleaned[:30]):
    print(f"{i}: {line}")
