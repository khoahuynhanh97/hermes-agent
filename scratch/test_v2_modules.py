"""Quick test for all new modules."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if sys.platform.startswith('win'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

print("="*55)
print("  HERMES v2 - QUICK MODULE VERIFICATION TEST")
print("="*55)

errors = []

# 1. AI Router
print("\n[1] Testing core/ai_router.py ...")
try:
    from core.ai_router import get_router, PROVIDERS
    router = get_router()
    status = router.get_status()
    print(f"    Providers loaded: {len(PROVIDERS)}")
    for pid, info in status.items():
        key_icon = "KEY" if info['has_key'] else "---"
        print(f"    [{key_icon}] {info['name']:25s} -> {info['status']}")
    print("    [OK] AI Router initialized!")
except Exception as e:
    errors.append(f"ai_router: {e}")
    print(f"    [FAIL] {e}")

# 2. TTS Engine
print("\n[2] Testing tools/tts_engine.py ...")
try:
    from tools.tts_engine import list_voices, VOICES_VI, synthesize_edge_tts
    voices = list_voices()
    print(f"    Available voices: {len(voices)}")
    for k, v in VOICES_VI.items():
        print(f"      {k}: {v}")
    print("    [OK] TTS Engine loaded!")
except Exception as e:
    errors.append(f"tts_engine: {e}")
    print(f"    [FAIL] {e}")

# 3. BGM Manager
print("\n[3] Testing tools/bgm_manager.py ...")
try:
    from tools.bgm_manager import PIXABAY_TRACKS, detect_tone_from_script
    tones = list(PIXABAY_TRACKS.keys())
    print(f"    BGM tones: {tones}")
    test_script = "Video nay vui ve va nang dong, nhay mua cung san pham"
    tone = detect_tone_from_script(test_script)
    print(f"    Tone detected from test script: '{tone}'")
    print("    [OK] BGM Manager loaded!")
except Exception as e:
    errors.append(f"bgm_manager: {e}")
    print(f"    [FAIL] {e}")

# 4. Background Swapper
print("\n[4] Testing editor/background_swapper.py ...")
try:
    from editor.background_swapper import swap_background, merge_audio
    print("    Functions: swap_background, merge_audio")
    print("    [OK] Background Swapper loaded!")
except Exception as e:
    errors.append(f"background_swapper: {e}")
    print(f"    [FAIL] {e}")

# 5. Style Profiler
print("\n[5] Testing core/style_profiler.py ...")
try:
    from core.style_profiler import build_profile, get_profile_summary, inject_style_into_prompt
    summary = get_profile_summary()
    print(f"    Profile summary: {summary[:80]}...")
    test_prompt = "Write a TikTok script"
    enhanced = inject_style_into_prompt(test_prompt)
    print(f"    Prompt injection: {'STYLE ADDED' if len(enhanced) > len(test_prompt) else 'No profile yet (OK)'}")
    print("    [OK] Style Profiler loaded!")
except Exception as e:
    errors.append(f"style_profiler: {e}")
    print(f"    [FAIL] {e}")

# 6. Job Watcher imports
print("\n[6] Testing core/job_watcher.py (imports) ...")
try:
    from core.job_watcher import JobWorker
    w = JobWorker()
    print("    JobWorker initialized with AI Router!")
    print("    [OK] Job Watcher loaded!")
except Exception as e:
    errors.append(f"job_watcher: {e}")
    print(f"    [FAIL] {e}")

# Summary
print("\n" + "="*55)
if errors:
    print(f"RESULT: {len(errors)} FAILED, {6-len(errors)} PASSED")
    for err in errors:
        print(f"  - {err}")
else:
    print("RESULT: ALL 6 MODULES PASSED!")
print("="*55)
