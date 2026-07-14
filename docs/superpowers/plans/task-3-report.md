# Task 3: Module 3 - Asset Pipeline Report

- **What you implemented:** 
  I implemented the `match_assets_to_script` function in `core/asset_pipeline.py`. It correctly reads a script JSON file, iterates over the scenes, mocks out matched asset files with their respective scene IDs, and writes a mapping file to the designated asset directory.
- **What you tested and test results:** 
  I tested the module by creating a dummy `script.json` file inside a temporary directory and ensuring that the function generates `scene_mapping.json` within the mock output directory as per requirements. The test passed fully (1 passed).
- **TDD Evidence:**
  - RED: `ModuleNotFoundError: No module named 'core'` when test run before implementation.
  - GREEN: `1 passed in 0.67s` when test run after implementation.
- **Files changed:**
  - Added `core/asset_pipeline.py`
  - Added `tests/core/test_asset_pipeline.py`
- **Self-review findings:**
  The implementation adheres accurately to the requirements in the brief. Type hinting and function docstrings are included. We're mocking out the matching process (using `f"mock_asset_{sid}.mp4"`) for now as detailed in the brief, which is standard practice for this step.
- **Any issues or concerns:**
  No concerns at the moment. Python module resolution requires `PYTHONPATH=.` (or running `python -m pytest`) so tests correctly discover the `core` package, which is standard for tests placed outside the module directory.

## Review Fixes Report

- **Fixes Implemented:**
  - `core/asset_pipeline.py`: Added a `try...except` block to handle `FileNotFoundError` and `json.JSONDecodeError`, returning `False` upon encountering them.
  - `core/asset_pipeline.py`: Added type checking using `isinstance(script, dict)` before accessing its keys. Defaulted to empty mapping behavior if it is not a dictionary.
  - `core/asset_pipeline.py`: Added check to gracefully skip scenes missing a `scene_id` or scenes that are not dictionaries, avoiding `"null"` keys in output mapping.
  - `tests/core/test_asset_pipeline.py`: Read the generated `scene_mapping.json` file in the success case and asserted that `scene_id` is properly mapped to the generated mock asset path. Added 4 new edge cases test checking for invalid file, invalid JSON, JSON root as list, and missing `scene_id`.
- **Test Results Post-Fixes:**
  - TDD Evidence: All newly added tests initially failed matching the faulty conditions.
  - Run `pytest tests/core/test_asset_pipeline.py -v`: 5 passed in 0.60s.
- **Commit SHA:** `f12c3d79fadd338a852d0cc55aa7c44a2b05d605`

## Review Fixes Report 2

- **Fixes Implemented:**
  - `core/asset_pipeline.py`: Moved `os.makedirs` down right before writing the mapping file so it doesn't create directories for invalid inputs.
  - `core/asset_pipeline.py`: Changed the validation logic so that if the JSON root is not a dict, it returns `False` instead of processing as empty. Also added explicit type checking for the `scenes` list.
  - `tests/core/test_asset_pipeline.py`: Updated `test_match_assets_to_script_root_list` to assert `False`.
- **Test Results Post-Fixes:**
  - `python -m pytest tests/core/test_asset_pipeline.py -v`: 5 passed in 0.32s.
- **Commit SHA:** `ae9323911a65367e13fc01d095e6f60cf6551618`
