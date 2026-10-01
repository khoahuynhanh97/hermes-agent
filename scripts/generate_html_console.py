import base64
import json
from pathlib import Path

def b64(p):
    path = Path(p)
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else ""

hub = Path(r"D:\work\VideoAI")
products = [
    {
        "brand": "Huawei",
        "model": "GT 2 Pro",
        "name": "Đồng hồ thông minh HUAWEI WATCH GT 2 Pro Pin Liền",
        "tag": "01/10/2026",
        "duration": "36.0s",
        "scenes_count": 6,
        "path": str(hub / "[Huawei] GT 2 Pro"),
        "keyframe_01": b64(hub / "[Huawei] GT 2 Pro" / "keyframes" / "scene_01.png"),
        "claims": [
            "Mặt kính Sapphire nguyên khối & khung vỏ Titanium chống trầy",
            "Thời lượng pin 14 ngày dùng liên tục",
            "100+ chế độ luyện tập & theo dõi sức khỏe 24/7",
        ],
        "caption": (hub / "[Huawei] GT 2 Pro" / "caption.txt").read_text(encoding="utf-8") if (hub / "[Huawei] GT 2 Pro" / "caption.txt").exists() else "",
    },
    {
        "brand": "Xiaomi",
        "model": "Robot Vacuum E10",
        "name": "Robot hút bụi lau nhà thông minh Xiaomi Robot Vacuum E10",
        "tag": "29/09/2026",
        "duration": "36.0s",
        "scenes_count": 6,
        "path": str(hub / "[Xiaomi] Robot Vacuum E10"),
        "keyframe_01": b64(hub / "[Xiaomi] Robot Vacuum E10" / "keyframes" / "scene_01.png"),
        "claims": [
            "Lực hút cực mạnh 4000Pa cuốn sạch mọi bụi bẩn",
            "Hút bụi & lau nhà 2 trong 1 với bình nước thông minh",
            "Thân máy siêu mỏng 8cm luồn sâu mọi gầm thấp",
        ],
        "caption": (hub / "[Xiaomi] Robot Vacuum E10" / "caption.txt").read_text(encoding="utf-8") if (hub / "[Xiaomi] Robot Vacuum E10" / "caption.txt").exists() else "",
    },
    {
        "brand": "JBL",
        "model": "PartyBox 310",
        "name": "Loa Bluetooth di động công suất lớn JBL PartyBox 310",
        "tag": "29/09/2026",
        "duration": "36.0s",
        "scenes_count": 6,
        "path": str(hub / "[JBL] PartyBox 310"),
        "keyframe_01": b64(hub / "[JBL] PartyBox 310" / "keyframes" / "scene_01.png"),
        "claims": [
            "Âm thanh JBL Pro Sound 240W uy lực bùng nổ",
            "Hệ thống đèn LED RGB đa sắc đồng bộ nhịp điệu",
            "Pin 18 giờ liên tục, tay kéo vali & bánh xe di động",
        ],
        "caption": (hub / "[JBL] PartyBox 310" / "caption.txt").read_text(encoding="utf-8") if (hub / "[JBL] PartyBox 310" / "caption.txt").exists() else "",
    },
]

html = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hermes Product Video Hub — Interactive Console</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {
      --background: #0f172a;
      --foreground: #f8fafc;
      --card: #1e293b;
      --border: #334155;
      --muted-foreground: #94a3b8;
      --primary: #3b82f6;
    }
    body {
      background-color: var(--background);
      color: var(--foreground);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
  </style>
</head>
<body class="p-4 sm:p-6 antialiased min-h-screen">
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-700/60 pb-4 gap-4">
      <div>
        <div class="flex items-center gap-2.5">
          <span class="text-2xl">🎬</span>
          <h1 class="text-xl font-bold tracking-tight text-slate-100">Hermes VideoAI Delivery Hub</h1>
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono border border-emerald-500/30 font-medium">3 Videos Ready</span>
        </div>
        <p class="text-xs text-slate-400 mt-1">
          Hệ thống điều hành sản xuất video sản phẩm AI — Grounded 30-50s, Storyboard Keyframes & Captions TikTok.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-xs font-mono text-slate-400 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700">📁 D:\\work\\VideoAI</span>
      </div>
    </header>

    <!-- Product Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
"""

for p in products:
    claims_html = "".join([f'<li class="flex items-start gap-1.5 text-xs text-slate-300"><span class="text-emerald-400 mt-0.5">✓</span><span>{c}</span></li>' for c in p["claims"]])
    caption_escaped = p["caption"].replace('"', '&quot;').replace("\n", "\\n")
    
    html += f"""
      <div class="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden shadow-lg flex flex-col justify-between hover:border-blue-500/80 transition-all duration-200">
        <div>
          <!-- Thumbnail Keyframe -->
          <div class="relative aspect-[9/16] max-h-72 bg-slate-950 flex items-center justify-center overflow-hidden border-b border-slate-700/60">
            <img src="{p['keyframe_01']}" class="object-contain w-full h-full" alt="{p['model']}">
            <div class="absolute top-2 left-2 bg-black/70 backdrop-blur-md px-2 py-0.5 rounded text-[10px] font-mono text-white border border-white/10 font-medium">
              ⏱ {p['duration']} • {p['scenes_count']} scenes
            </div>
            <div class="absolute top-2 right-2 bg-blue-600/90 backdrop-blur-md px-2 py-0.5 rounded text-[10px] font-semibold text-white">
              [{p['brand']}]
            </div>
          </div>

          <!-- Body Info -->
          <div class="p-4 space-y-3">
            <div>
              <div class="flex items-center justify-between">
                <span class="text-xs font-mono text-blue-400 font-semibold">[{p['brand']}] {p['model']}</span>
                <span class="text-[10px] text-slate-400 font-mono bg-slate-900/60 px-2 py-0.5 rounded">{p['tag']}</span>
              </div>
              <h3 class="text-sm font-bold text-slate-100 mt-1 line-clamp-2 leading-snug">{p['name']}</h3>
            </div>

            <!-- Claims -->
            <div class="bg-slate-900/70 p-3 rounded-lg border border-slate-700/60 space-y-1.5">
              <div class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Điểm nổi bật đã xác thực:</div>
              <ul class="space-y-1">
                {claims_html}
              </ul>
            </div>
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="p-4 pt-0 border-t border-slate-700/40 mt-3 space-y-2">
          <button onclick="navigator.clipboard.writeText(`{caption_escaped}`); alert('Đã sao chép caption TikTok của {p['model']}!');" class="w-full text-xs py-2 px-3 bg-slate-700/60 hover:bg-slate-700 border border-slate-600 rounded-lg font-medium text-slate-200 transition-colors flex items-center justify-center gap-1.5 active:scale-98">
            <span>📋</span> Sao chép Caption TikTok
          </button>
        </div>
      </div>
"""

html += """
    </div>
  </div>
</body>
</html>"""

out_dir = Path(r"C:\Users\ninak\.gemini\antigravity\brain\372d8283-211b-4d55-8419-d2db3b4de1fb")
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / "video_hub_console.html"
out_file.write_text(html, encoding="utf-8")

hub_index = Path(r"D:\work\VideoAI\index.html")
hub_index.write_text(html, encoding="utf-8")

print(f"Generated successfully:\n - {out_file}\n - {hub_index}")
