import os
import re
import unicodedata
from pathlib import Path

def to_slug(text):
    """Converts Vietnamese and special character strings into a clean ASCII URL-friendly slug."""
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    
    # Map lowercase accented Vietnamese characters to their ASCII equivalents
    viet_map = {
        'à':'a','á':'a','ả':'a','ã':'a','ạ':'a','ă':'a','ằ':'a','ắ':'a','ẳ':'a','ẵ':'a','ặ':'a','â':'a','ầ':'a','ấ':'a','ẩ':'a','ẫ':'a','ậ':'a',
        'đ':'d',
        'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e','ê':'e','ề':'e','ế':'e','ể':'e','ễ':'e','ệ':'e',
        'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
        'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o','ô':'o','ồ':'o','ố':'o','ổ':'o','ỗ':'o','ộ':'o','ơ':'o','ờ':'o','ớ':'o','ở':'o','ỡ':'o','ợ':'o',
        'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u','ư':'u','ừ':'u','ứ':'u','ử':'u','ữ':'u','ự':'u',
        'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y'
    }
    
    res = []
    for c in text.lower():
        if c in viet_map:
            res.append(viet_map[c])
        else:
            res.append(c)
    text = "".join(res)
    
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    # Collapse multiple spaces or hyphens into a single hyphen
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    
    if not text:
        text = "product"
    return text

def clean_filename(filename):
    """Filters special characters to make a safe filename for disk storage."""
    return re.sub(r'[\\/*?:"<>| ]', '_', filename)

def create_directory_structure(project_path):
    """Creates the standard directory structure for a project."""
    paths = [
        os.path.join(project_path, 'Phoi'),
        os.path.join(project_path, 'clips'),
        os.path.join(project_path, 'audio'),
        os.path.join(project_path, 'scripts'),
        os.path.join(project_path, 'exports')
    ]
    for p in paths:
        os.makedirs(p, exist_ok=True)
    return paths

def list_downloaded_materials(materials_dir):
    """Lists all video materials (.mp4, .mkv, .avi, etc.) in the project's materials folder."""
    if not os.path.exists(materials_dir):
        return []
    valid_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
    materials = []
    for file in os.listdir(materials_dir):
        ext = os.path.splitext(file)[1].lower()
        if ext in valid_exts:
            materials.append(os.path.abspath(os.path.join(materials_dir, file)))
    return materials

def list_generated_clips(clips_dir):
    """Lists all video clips (.mp4, etc.) in the project's clips folder."""
    if not os.path.exists(clips_dir):
        return []
    valid_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
    clips = []
    for file in os.listdir(clips_dir):
        ext = os.path.splitext(file)[1].lower()
        if ext in valid_exts:
            clips.append(os.path.abspath(os.path.join(clips_dir, file)))
    return clips
