import os
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config
from hermes.application.core.file_manager import to_slug, create_directory_structure

class ProjectManager:
    def __init__(self):
        # Resolve projects root directory relative to the config file location
        config_dir = os.path.dirname(os.path.abspath(config.__file__))
        
        # If PROJECTS_ROOT is absolute, use it. Otherwise, join with config directory
        if os.path.isabs(config.PROJECTS_ROOT):
            self.projects_root = config.PROJECTS_ROOT
        else:
            self.projects_root = os.path.abspath(os.path.join(config_dir, config.PROJECTS_ROOT))
            
        os.makedirs(self.projects_root, exist_ok=True)

    def get_projects_root(self):
        return self.projects_root

    def list_projects(self):
        """Lists all project slugs by scanning the projects root directory."""
        if not os.path.exists(self.projects_root):
            return []
        
        projects = []
        for name in os.listdir(self.projects_root):
            p_dir = os.path.join(self.projects_root, name)
            if os.path.isdir(p_dir):
                meta_path = os.path.join(p_dir, 'metadata.json')
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            projects.append({
                                'slug': name,
                                'name': meta.get('product_name', name),
                                'path': p_dir
                            })
                    except Exception:
                        projects.append({
                            'slug': name,
                            'name': name,
                            'path': p_dir
                        })
        return projects

    def get_project_path(self, product_name):
        """Generates project path from product name using its slug."""
        slug = to_slug(product_name)
        return os.path.join(self.projects_root, slug), slug

    def initialize_project(self, product_name, description="", price="", selling_points="", target_audience="", pain_points=""):
        """Initializes folders and metadata.json for a new product project."""
        project_dir, slug = self.get_project_path(product_name)
        create_directory_structure(project_dir)

        existing_metadata = self.get_metadata(slug)
        metadata = existing_metadata or {
            "product_name": product_name,
            "product_slug": slug,
            "description": description,
            "price": price,
            "selling_points": selling_points,
            "target_audience": target_audience,
            "pain_points": pain_points,
            "keywords": {"vi": [], "en": [], "zh": []},
            "scripts": {},
            "audio": {},
            "clips": [],
            "exports": {}
        }

        metadata["product_name"] = product_name
        metadata["product_slug"] = slug
        for key, value in {
            "description": description,
            "price": price,
            "selling_points": selling_points,
            "target_audience": target_audience,
            "pain_points": pain_points,
        }.items():
            if value or not existing_metadata:
                metadata[key] = value
        metadata.setdefault("keywords", {"vi": [], "en": [], "zh": [], "manual": []})
        metadata["keywords"].setdefault("vi", [])
        metadata["keywords"].setdefault("en", [])
        metadata["keywords"].setdefault("zh", [])
        metadata["keywords"].setdefault("manual", [])
        metadata.setdefault("scripts", {})
        metadata.setdefault("audio", {})
        metadata.setdefault("clips", [])
        metadata.setdefault("exports", {})
        
        self.save_metadata(slug, metadata)
        return project_dir, slug

    def get_metadata(self, slug):
        """Loads and returns metadata dict for a specific project slug."""
        project_dir = os.path.join(self.projects_root, slug)
        clips_dir = os.path.join(project_dir, 'clips')
        os.makedirs(clips_dir, exist_ok=True)
        
        meta_path = os.path.join(project_dir, 'metadata.json')
        if not os.path.exists(meta_path):
            return None
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                if "clips" not in meta:
                    meta["clips"] = []
                return meta
        except Exception as e:
            print(f"[x] Error loading metadata for {slug}: {e}")
            return None

    def save_metadata(self, slug, metadata):
        """Saves metadata dict to metadata.json in the project folder."""
        project_dir = os.path.join(self.projects_root, slug)
        os.makedirs(project_dir, exist_ok=True)
        meta_path = os.path.join(project_dir, 'metadata.json')
        
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[x] Error saving metadata for {slug}: {e}")
            return False

    def get_project_folders(self, slug):
        """Returns a dict of paths inside the project slug folder."""
        p_dir = os.path.join(self.projects_root, slug)
        os.makedirs(os.path.join(p_dir, 'clips'), exist_ok=True)
        
        materials_dir = os.path.join(p_dir, 'Phoi')
        old_materials_dir = os.path.join(p_dir, 'materials')
        
        # Backward compatibility: Rename existing 'materials' folder to 'Phoi' if it exists
        if os.path.exists(old_materials_dir) and not os.path.exists(materials_dir):
            try:
                os.rename(old_materials_dir, materials_dir)
            except Exception:
                pass
                
        # Double check which one actually exists to set path correctly
        if not os.path.exists(materials_dir) and os.path.exists(old_materials_dir):
            materials_dir = old_materials_dir
            
        return {
            "root": p_dir,
            "materials": materials_dir,
            "clips": os.path.join(p_dir, 'clips'),
            "audio": os.path.join(p_dir, 'audio'),
            "scripts": os.path.join(p_dir, 'scripts'),
            "exports": os.path.join(p_dir, 'exports'),
            "metadata_file": os.path.join(p_dir, 'metadata.json')
        }
