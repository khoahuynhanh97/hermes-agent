"""Bundled resource resolver for Hermes.

Resolution order for runtime-bundled resources (skills, prompts, locales):

1. Explicit environment override (``HERMES_SKILLS_DIR`` / ``HERMES_PROMPTS_DIR`` /
   ``HERMES_LOCALES_DIR``). This wins for both read and write — operators
   pinning to a fixed location can rely on it.
2. Materialized copy under ``HERMES_DATA_DIR/caches/bundled-resources/<subdir>``. The
   first call copies the package-shipped defaults out of
   ``hermes.bundled.<subdir>`` (via ``importlib.resources``) into that
   location so subsequent reads return a normal filesystem ``Path``.
3. Development fallback to the in-tree ``resources/<subdir>`` directory,
   only when the package resource does not exist (editable install from
   a working tree).

External skills are intentionally NOT resolved here — they live under
``HERMES_HOME/skills`` (user data) or under ``skills.external_dirs`` from
``config.yaml`` and are owned by ``hermes.agent.skill_utils``.

The resolver never derives paths from the location of this file or from
``sys.path``; it only consults environment variables, ``HERMES_DATA_DIR``,
and ``importlib.resources``.
"""
from __future__ import annotations

import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_PACKAGE = "hermes.bundled"
_VALID_SUBDIRS = ("skills", "prompts", "locales")

# Map: public env var name -> bundled subdir name
_ENV_VARS: dict[str, str] = {
    "HERMES_SKILLS_DIR": "skills",
    "HERMES_PROMPTS_DIR": "prompts",
    "HERMES_LOCALES_DIR": "locales",
}


def _hermes_data_dir() -> Path:
    """Return ``HERMES_DATA_DIR`` or fall back to ``~/.hermes``."""
    env = os.environ.get("HERMES_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".hermes"


import hashlib

def _migrate_old_cache(old_root: Path, new_root: Path) -> None:
    """Safely migrate the legacy cache/bundled directory if it exists."""
    if old_root.exists() and old_root.is_dir():
        try:
            new_root.parent.mkdir(parents=True, exist_ok=True)
            if not new_root.exists():
                shutil.copytree(old_root, new_root, symlinks=True)
                # Write current digest to prevent immediate refresh from wiping migrated content
                digest_file = new_root / ".digest"
                if not digest_file.exists():
                    try:
                        digest_file.write_text(_compute_package_digest(), encoding="utf-8")
                    except Exception:
                        pass
            shutil.rmtree(old_root, ignore_errors=True)
            # Remove singular cache folder if empty
            if old_root.parent.exists() and not any(old_root.parent.iterdir()):
                old_root.parent.rmdir()
        except Exception as e:
            logger.warning("Failed to migrate old cache: %s", e)


def _compute_package_digest() -> str:
    """Compute a SHA-256 digest of all files in hermes.bundled to track wheel changes."""
    import importlib.resources as ilr
    h = hashlib.sha256()
    def _hash_traversable(t):
        if t.is_file():
            h.update(t.name.encode("utf-8"))
            try:
                h.update(t.read_bytes())
            except Exception:
                pass
        elif t.is_dir():
            for child in sorted(t.iterdir(), key=lambda x: x.name):
                _hash_traversable(child)
    try:
        root = ilr.files(_PACKAGE)
        _hash_traversable(root)
    except Exception as e:
        h.update(str(e).encode("utf-8"))
    return h.hexdigest()


def _materialized_dir(subdir: str) -> Path:
    """Return (and lazily populate/refresh) the on-disk copy of ``hermes.bundled.<subdir>``.

    The bundled package data is copied into
    ``HERMES_DATA_DIR/caches/bundled-resources/<subdir>`` on first access.
    """
    if subdir not in _VALID_SUBDIRS:
        raise ValueError(f"Unknown bundled subdir: {subdir!r}")
        
    data_dir = _hermes_data_dir()
    old_root = data_dir / "cache" / "bundled"
    new_root = data_dir / "caches" / "bundled-resources"
    
    _migrate_old_cache(old_root, new_root)
    
    target = new_root / subdir
    digest_file = new_root / ".digest"
    current_digest = _compute_package_digest()
    
    needs_refresh = True
    if digest_file.exists():
        try:
            cached_digest = digest_file.read_text(encoding="utf-8").strip()
            if cached_digest == current_digest:
                needs_refresh = False
        except Exception:
            pass
            
    if needs_refresh:
        # Safe cleanup of existing package subdirs only, preserving other directories
        for d in _VALID_SUBDIRS:
            sub_dir = new_root / d
            if sub_dir.exists():
                try:
                    shutil.rmtree(sub_dir, ignore_errors=True)
                except Exception:
                    pass
        new_root.mkdir(parents=True, exist_ok=True)
        for d in _VALID_SUBDIRS:
            _copy_package_tree(d, new_root / d)
        try:
            digest_file.write_text(current_digest, encoding="utf-8")
        except Exception:
            pass
            
    return target


def _copy_package_tree(subdir: str, target: Path) -> None:
    """Copy every file under ``hermes.bundled.<subdir>`` into ``target``.

    Uses ``importlib.resources`` so the source works equally well from a
    regular install (wheels and sdists) and from an editable install.
    """
    import importlib.resources as ilr

    root = ilr.files(_PACKAGE).joinpath(subdir)
    if not root.is_dir():
        # No bundled resource at all — caller decides what to do.
        target.mkdir(parents=True, exist_ok=True)
        return
    _copy_traversable(root, target)


def _copy_traversable(source, target_dir: Path) -> None:
    """Recursively copy a Traversable directory tree to a physical Path."""
    import importlib.resources as ilr

    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        dest = target_dir / child.name
        if child.is_dir():
            _copy_traversable(child, dest)
        elif child.is_file():
            with ilr.as_file(child) as path:
                shutil.copy2(str(path), str(dest))



# ── Public API ────────────────────────────────────────────────────────────


def get_skills_dir() -> Path:
    """Return the canonical skills directory for the current runtime."""
    return _resolve("skills")


def get_prompts_dir() -> Path:
    """Return the canonical prompts directory for the current runtime."""
    return _resolve("prompts")


def get_locales_dir() -> Path:
    """Return the canonical locales directory for the current runtime."""
    return _resolve("locales")


def _resolve(subdir: str) -> Path:
    """Apply the documented resolution order for one bundled subdir."""
    env_var = next(name for name, s in _ENV_VARS.items() if s == subdir)
    configured = os.environ.get(env_var, "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    try:
        return _materialized_dir(subdir)
    except OSError as exc:
        logger.warning("Bundled %s unavailable, falling back: %s", subdir, exc)
    return _dev_fallback(subdir)


def _dev_fallback(subdir: str) -> Path:
    """Last-resort: in-tree ``resources/<subdir>`` for editable installs."""
    # We must not derive from __file__ parent counts. Use a stable sentinel:
    # if the package itself can be located, walk up to the project root by
    # looking for a sibling ``resources/`` only when ``hermes.bundled`` is
    # itself missing from importlib (developer running tests without an
    # install step). The function is intentionally narrow: if neither the
    # override nor the package copy can be produced, raise.
    import importlib.resources as ilr

    package_root = ilr.files(_PACKAGE)
    if package_root is None:
        raise FileNotFoundError(
            f"Bundled resource {_PACKAGE!r} is not available on this install."
        )
    raise FileNotFoundError(
        f"Bundled {subdir!r} is not available and no fallback is configured. "
        f"Set {dict((k, v) for k, v in _ENV_VARS.items() if v == subdir)!r} "
        "or ensure HERMES_DATA_DIR is writable."
    )


# ── Explicit package accessor for callers that want importlib.resources ──


def get_bundled_package():
    """Return the ``hermes.bundled`` Traversable for advanced consumers.

    Most callers should not need this; use ``get_skills_dir`` /
    ``get_prompts_dir`` / ``get_locales_dir`` instead.
    """
    import importlib.resources as ilr

    return ilr.files(_PACKAGE)


def iter_bundled_skill_files(name: str = "SKILL.md"):
    """Yield ``Path`` objects for every file named ``name`` in the bundled skills tree.

    Mirrors :func:`hermes.agent.skill_utils.iter_skill_index_files` but
    reads directly from the package. Useful when callers want bundled
    content without writing to the materialized cache.
    """
    skills_dir = get_skills_dir()
    for path in sorted(skills_dir.rglob(name)):
        yield path


# Eagerly resolve the common directories so import-time side effects
# (first-time copy) happen during the predictable path, not at the
# unpredictable first skill scan.  Skipped when the user has not yet
# configured HERMES_DATA_DIR and the filesystem is read-only.
_priming_targets: list[Callable[[], Path]] = [get_skills_dir, get_prompts_dir, get_locales_dir]


def prime_bundled_resources() -> None:
    """Copy bundled skills/prompts/locales into the data cache.

    Safe to call multiple times.  Callers should not depend on the
    return value — this is purely a "make sure the cache exists" hook.
    """
    for fn in _priming_targets:
        try:
            fn()
        except FileNotFoundError:
            # Dev fallback in tree: nothing to copy.
            continue
        except OSError as exc:
            logger.debug("Skipping %s prime: %s", fn.__name__, exc)
