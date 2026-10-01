#!/usr/bin/env python3
"""
Refactor handlers.py (2,866 lines) into modular structure.

Strategy:
1. Keep handlers_monolith.py as backup
2. Convert handlers.py into handlers/ package
3. Split into focused modules by responsibility
4. Create __init__.py that re-exports everything for backward compatibility
"""

import re
from pathlib import Path

def main():
    base_dir = Path("D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video")
    monolith = base_dir / "handlers_monolith.py"
    handlers_dir = base_dir / "handlers"
    
    if not monolith.exists():
        print(f"Error: {monolith} not found")
        return 1
    
    # Read the monolithic file
    print(f"Reading {monolith}...")
    content = monolith.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    print(f"Total lines: {len(lines)}")
    
    # Create handlers directory
    handlers_dir.mkdir(exist_ok=True)
    print(f"Created {handlers_dir}")
    
    # Extract imports - find where imports end (before logger = ...)
    imports_end = 63  # Line with "logger = logging.getLogger(__name__)"
    for i, line in enumerate(lines[:100]):
        if 'logger = logging.getLogger' in line:
            imports_end = i + 2  # Include logger line and blank line after
            break
    
    imports = "".join(lines[:imports_end])
    print(f"Extracted imports ({imports_end} lines)")
    
    # Define module splits based on method boundaries
    # Format: (start_line_0indexed, end_line_0indexed, module_name, description)
    splits = [
        # Helper functions before class
        (imports_end, 667, "common.py", "Common helper functions and config builders"),
        
        # Class definition and init
        (667, 803, "_base.py", "ProductVideoJobHandlers class definition and init"),
        
        # QC-related methods
        (803, 1010, "qc_handler.py", "QC retry and preview handlers"),
        
        # Research phase
        (1010, 1264, "research_handler.py", "Research, resource pack, and lock handlers"),
        
        # Creative phase
        (1264, 1884, "creative_handler.py", "Creative brief, scene plan, and storyboard handlers"),
        
        # Render phase
        (1884, 2102, "render_handler.py", "Video rendering handler"),
        
        # Export phase
        (2102, 2247, "export_handler.py", "Video export handler"),
        
        # Class utility methods
        (2247, 2298, "_base.py", "Handler dispatch and utility methods (append to _base.py)"),
        
        # Module-level functions
        (2298, len(lines), "registry.py", "Module-level registration and workflow starter functions"),
    ]
    
    # Extract each module
    modules_created = {}
    
    for start, end, module_name, description in splits:
        if module_name in modules_created:
            # Append mode
            print(f"Appending to {module_name}: lines {start+1}-{end} ({description})")
            existing_content = (handlers_dir / module_name).read_text(encoding="utf-8")
            new_content = "".join(lines[start:end])
            combined = existing_content + "\n\n" + new_content
            (handlers_dir / module_name).write_text(combined, encoding="utf-8")
        else:
            # Create new module
            print(f"Creating {module_name}: lines {start+1}-{end} ({description})")
            module_content = imports + "\n\n" + "".join(lines[start:end])
            (handlers_dir / module_name).write_text(module_content, encoding="utf-8")
            modules_created[module_name] = True
    
    # Create __init__.py that re-exports everything
    init_content = '''"""Product Video job handlers - modular implementation.

This package splits the monolithic handlers.py (2,866 lines) into focused modules:
- common.py: Shared helper functions and config builders
- _base.py: ProductVideoJobHandlers base class and infrastructure
- qc_handler.py: QC retry and preview handlers (methods)
- research_handler.py: Research, resource pack, and lock handlers (methods)
- creative_handler.py: Creative brief, scene plan, and storyboard handlers (methods)
- render_handler.py: Video rendering handler (methods)
- export_handler.py: Video export handler (methods)
- registry.py: Module-level registration and workflow starter functions

All methods are mixed into the ProductVideoJobHandlers class via the _base module.
Public API is re-exported here for backward compatibility.
"""
from __future__ import annotations

# Import the main class from base
from hermes_personal.product_video.handlers._base import ProductVideoJobHandlers

# Import module-level functions from registry
from hermes_personal.product_video.handlers.registry import (
    create_product_video_topic_handlers,
    register_product_video_job_handlers,
    start_product_video_workflow,
)

# Import public utilities from common
from hermes_personal.product_video.handlers.common import (
    verify_job_digests,
    create_configured_creative_generator,
)

# Re-export for backward compatibility
__all__ = [
    "ProductVideoJobHandlers",
    "create_product_video_topic_handlers",
    "register_product_video_job_handlers",
    "start_product_video_workflow",
    "verify_job_digests",
    "create_configured_creative_generator",
]
'''
    
    (handlers_dir / "__init__.py").write_text(init_content, encoding="utf-8")
    print(f"Created __init__.py")
    
    # Now we need to fix the _base.py to properly include all methods
    # The methods from qc_handler, research_handler, etc. need to be part of the class
    print("\nPost-processing: Merging handler methods into ProductVideoJobHandlers class...")
    
    # Read _base.py
    base_content = (handlers_dir / "_base.py").read_text(encoding="utf-8")
    
    # Read each handler module and extract methods
    handler_modules = [
        "qc_handler.py",
        "research_handler.py", 
        "creative_handler.py",
        "render_handler.py",
        "export_handler.py",
    ]
    
    all_methods = []
    for handler_file in handler_modules:
        handler_path = handlers_dir / handler_file
        if handler_path.exists():
            handler_content = handler_path.read_text(encoding="utf-8")
            # Extract method definitions (indented with 4 spaces)
            method_lines = []
            in_method = False
            for line in handler_content.splitlines(keepends=True):
                if line.startswith('    def '):
                    in_method = True
                    method_lines.append(line)
                elif in_method:
                    if line.strip() and not line.startswith(' '):
                        # End of method
                        in_method = False
                    else:
                        method_lines.append(line)
            
            if method_lines:
                all_methods.append(f"\n    # Methods from {handler_file}\n")
                all_methods.extend(method_lines)
    
    # Insert methods before the last line of _base.py (before final utility methods)
    # Find the position to insert (after __init__ but before get_handlers_map)
    base_lines = base_content.splitlines(keepends=True)
    insert_pos = len(base_lines)
    for i, line in enumerate(base_lines):
        if '    def get_handlers_map(' in line or '    def dispatch_registered_job(' in line:
            insert_pos = i
            break
    
    new_base_lines = base_lines[:insert_pos] + all_methods + base_lines[insert_pos:]
    (handlers_dir / "_base.py").write_text("".join(new_base_lines), encoding="utf-8")
    
    print("✓ Post-processing complete")
    
    # Verify file sizes
    print("\nModule sizes:")
    for py_file in sorted(handlers_dir.glob("*.py")):
        line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        print(f"  {py_file.name:25} {line_count:5} lines")
    
    print(f"\n✓ Refactoring complete!")
    print(f"  Original: {len(lines)} lines")
    print(f"  Modules created: {len(list(handlers_dir.glob('*.py')))}")
    print(f"\nBackup: {monolith}")
    print(f"New package: {handlers_dir}")
    
    return 0

if __name__ == "__main__":
    exit(main())
