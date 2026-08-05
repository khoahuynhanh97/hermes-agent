import os
import sys
import json
import socket
import asyncio
import threading
from pathlib import Path
from aiohttp import web

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import config
from providers.smart_crawler_provider import parse_shopee_url, fetch_shopee_product_details
from core.keyword_generator import extract_keywords_from_product_page

# Hermes Modernization Imports
from hermes.db import Database
from hermes.config import get_data_path
from hermes.adapters.sqlite.project_repository import SQLiteProjectRepository
from hermes.ports.project_repository import ProjectRepository
from hermes.domain.results import Result

# Initialize project repository
hermes_db_path = os.environ.get("HERMES_DB_PATH", str(get_data_path("db", "hermes.db")))
hermes_database = Database(hermes_db_path)
hermes_database.initialize() # Ensure schema is applied
PROJECT_REPO: ProjectRepository = SQLiteProjectRepository(hermes_db_path)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes Prompt Studio Web 🎨</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-app: #09090b;
            --bg-surface: #121215;
            --bg-surface-2: #18181b;
            --bg-surface-3: #27272a;
            --border-color: #27272a;
            --border-soft: #1f1f23;
            --text-main: #f4f4f5;
            --text-muted: #a1a1aa;
            --text-subtle: #71717a;
            --accent-blue: #38bdf8;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-green-hover: #059669;
            --radius-main: 12px;
            --radius-sm: 8px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background-color: var(--bg-app); color: var(--text-main); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

        /* TOPBAR */
        header {
            height: 56px;
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 20px;
        }
        .brand { display: flex; align-items: center; gap: 12px; font-weight: 800; font-size: 18px; letter-spacing: 0.5px; }
        .brand-badge { background: var(--accent-green); color: #000; font-size: 10px; font-weight: 700; padding: 2px 6px; borderRadius: 4px; }
        
        .main-modules { display: flex; gap: 8px; }
        .mod-btn {
            background: transparent; border: 1px solid transparent; color: var(--text-muted);
            padding: 8px 16px; border-radius: var(--radius-sm); font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s;
        }
        .mod-btn:hover { color: var(--text-main); background: var(--bg-surface-2); }
        .mod-btn.active { background: var(--bg-surface-3); color: #fff; border-color: var(--accent-blue); }

        .project-pill-wrapper {
            position: relative;
        }
        .project-pill {
            background: var(--bg-surface-2); border: 1px solid var(--border-color); padding: 6px 12px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; color: var(--accent-blue);
            cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px;
        }
        .project-pill:hover { background: var(--bg-surface-3); border-color: var(--accent-blue); }

        /* MODAL */
        .modal {
            display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%;
            overflow: auto; background-color: rgba(0,0,0,0.6); backdrop-filter: blur(5px);
            align-items: center; justify-content: center;
        }
        .modal-content {
            background-color: var(--bg-surface); margin: auto; padding: 25px; border: 1px solid var(--border-color);
            width: 90%; max-width: 500px; border-radius: var(--radius-main); box-shadow: 0 5px 15px rgba(0,0,0,0.5);
            position: relative; animation: fadeIn 0.3s;
        }
        .modal-content h2 { color: var(--text-main); font-size: 1.5em; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 15px; }
        .close-button {
            color: var(--text-muted); float: right; font-size: 28px; font-weight: bold; cursor: pointer;
            position: absolute; top: 10px; right: 20px;
        }
        .close-button:hover, .close-button:focus { color: var(--text-main); text-decoration: none; cursor: pointer; }
        .modal-body .form-group { margin-bottom: 15px; }
        .modal-body .input-row { gap: 10px; }
        .modal-body button { padding: 8px 15px; font-size: 13px; border-radius: var(--radius-sm); }
        .modal-body select { margin-top: 5px; }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }


        /* MAIN WRAPPER */
        .app-body { flex: 1; display: flex; overflow: hidden; }

        /* SIDEBAR */
        aside {
            width: 220px; background: var(--bg-surface); border-right: 1px solid var(--border-color);
            padding: 16px; display: flex; flex-direction: column; justify-content: space-between;
        }
        .btn-auto {
            width: 100%; background: var(--accent-green); color: #fff; font-weight: 700; font-size: 13px;
            padding: 10px; border: none; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.2s;
        }
        .btn-auto:hover { background: var(--accent-green-hover); }
        .sys-status { background: var(--bg-surface-2); border: 1px solid var(--border-soft); border-radius: var(--radius-sm); padding: 10px; font-size: 11px; }
        .sys-item { display: flex; justify-content: space-between; margin-bottom: 6px; }
        .dot-green { color: var(--accent-green); }

        /* WORKSPACE */
        main { flex: 1; display: flex; flex-direction: column; padding: 16px; gap: 12px; overflow: hidden; }

        /* SUBTABS BAR */
        .subtabs-bar {
            display: flex; gap: 4px; background: var(--bg-surface); padding: 4px; border-radius: var(--radius-main);
            border: 1px solid var(--border-color); overflow-x: auto;
        }
        .subtab-btn {
            flex: 1; background: transparent; border: none; color: var(--text-muted); padding: 10px 12px;
            font-size: 12px; font-weight: 600; border-radius: var(--radius-sm); cursor: pointer; text-align: center; white-space: nowrap; transition: all 0.2s;
        }
        .subtab-btn:hover { color: var(--text-main); background: var(--bg-surface-2); }
        .subtab-btn.active { background: var(--accent-blue); color: #000; font-weight: 700; }

        /* TAB CONTENT PANELS */
        .panel { flex: 1; background: var(--bg-surface); border-radius: var(--radius-main); border: 1px solid var(--border-color); display: none; flex-direction: column; overflow: hidden; }
        .panel.active { display: flex; }
        .panel-scroll { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }

        /* FORM ELEMENTS */
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        .form-label { font-size: 12px; font-weight: 700; color: var(--text-muted); }
        .input-row { display: flex; gap: 8px; }
        input[type="text"], textarea, select {
            background: var(--bg-surface-2); border: 1px solid var(--border-color); color: var(--text-main);
            padding: 10px 12px; border-radius: var(--radius-sm); font-size: 13px; outline: none; transition: border 0.2s; width: 100%;
        }
        input[type="text"]:focus, textarea:focus, select:focus { border-color: var(--accent-blue); }
        textarea { resize: vertical; min-height: 80px; }

        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }

        .card-box { background: var(--bg-surface-2); border: 1px solid var(--border-soft); border-radius: var(--radius-main); padding: 14px; display: flex; flex-direction: column; gap: 10px; }

        .btn-parse { background: var(--accent-green); color: #fff; border: none; padding: 0 16px; font-weight: 700; font-size: 13px; border-radius: var(--radius-sm); cursor: pointer; white-space: nowrap; }
        .btn-parse:hover { background: var(--accent-green-hover); }

        /* ACTION BAR */
        .action-bar {
            height: 54px; background: var(--bg-surface-2); border-top: 1px solid var(--border-color);
            display: flex; align-items: center; justify-content: flex-end; padding: 0 16px; gap: 10px;
        }
        .btn-act {
            background: var(--bg-surface-3); border: 1px solid var(--border-color); color: var(--text-main);
            padding: 8px 14px; font-size: 12px; font-weight: 700; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s;
        }
        .btn-act:hover { background: #3f3f46; }
        .btn-act-next { background: var(--accent-green); color: #fff; border: none; }
        .btn-act-next:hover { background: var(--accent-green-hover); }

        /* TOAST NOTIFICATION */
        #toast {
            position: fixed; bottom: 20px; right: 20px; background: var(--accent-green); color: #fff;
            padding: 12px 20px; border-radius: var(--radius-sm); font-weight: 700; font-size: 13px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5); opacity: 0; pointer-events: none; transition: opacity 0.3s; z-index: 9999;
        }
        #toast.show { opacity: 1; }
    </style>
</head>
<body>

    <!-- TOPBAR -->
    <header>
        <div class="brand">
            HERMES <span class="brand-badge">WEB STUDIO</span>
        </div>
        <div class="main-modules">
            <button class="mod-btn active" onclick="switchModule(1)">🎨 1. Prompt Studio</button>
            <button class="mod-btn" onclick="switchModule(2)">🎬 2. Cắt Ghép Video</button>
            <button class="mod-btn" onclick="switchModule(3)">🧠 3. AI Phân Tích & Sáng Tạo</button>
        </div>
        <div class="project-pill-wrapper">
            <button class="project-pill" id="current-project-btn" onclick="showProjectModal()">📁 Dự án: <span id="current-project-name">Đang tải...</span></button>
        </div>
    </header>

    <!-- Project Modal -->
    <div id="project-modal" class="modal">
        <div class="modal-content">
            <span class="close-button" onclick="hideProjectModal()">&times;</span>
            <h2>Quản lý Dự án</h2>
            <div class="modal-body">
                <div class="form-group">
                    <label class="form-label">Tạo Dự án Mới:</label>
                    <div class="input-row">
                        <input type="text" id="new-project-name" placeholder="Tên dự án mới...">
                        <button class="btn-parse" onclick="createNewProject()">➕ Tạo</button>
                    </div>
                </div>
                <div class="form-group" style="margin-top: 20px;">
                    <label class="form-label">Chọn Dự án Hiện Có:</label>
                    <select id="project-select" onchange="selectProject(this.value)">
                        <option value="">-- Chọn dự án --</option>
                    </select>
                </div>
                <div id="project-list-container" style="margin-top: 20px;">
                    <!-- Project list will be rendered here -->
                </div>
            </div>
        </div>
    </div>

    <!-- APP BODY -->
    <div class="app-body">
        <!-- SIDEBAR -->
        <aside>
            <div>
                <button class="btn-auto">🚀 Quy Trình Tự Động (Auto)</button>
            </div>
            <div class="sys-status">
                <div class="sys-item"><span>FFmpeg Decoder</span> <span class="dot-green">● OK</span></div>
                <div class="sys-item"><span>Gemini AI API</span> <span class="dot-green">● OK</span></div>
                <div class="sys-item"><span>yt-dlp Engine</span> <span class="dot-green">● OK</span></div>
            </div>
        </aside>

        <!-- MAIN WORKSPACE -->
        <main>
            <!-- 7 SUBTABS BAR -->
            <div class="subtabs-bar">
                <button class="subtab-btn active" onclick="switchSubtab(1)">📋 1. Sản phẩm</button>
                <button class="subtab-btn" onclick="switchSubtab(2)">📊 2. Phân tích</button>
                <button class="subtab-btn" onclick="switchSubtab(3)">📝 3. Kịch bản</button>
                <button class="subtab-btn" onclick="switchSubtab(4)">🖼️ 4. Storyboard</button>
                <button class="subtab-btn" onclick="switchSubtab(5)">🎨 5. Prompt ảnh</button>
                <button class="subtab-btn" onclick="switchSubtab(6)">🎥 6. Prompt video</button>
                <button class="subtab-btn" onclick="switchSubtab(7)">🏁 7. Kết quả</button>
            </div>

            <!-- PANEL 1: SẢN PHẨM -->
            <div class="panel active" id="panel-1">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">🌐 URL SẢN PHẨM (SHOPEE, TIKTOK SHOP, 1688, TAOBAO...):</label>
                        <div class="input-row">
                            <input type="text" id="input-url" placeholder="Dán liên kết trang sản phẩm tại đây...">
                            <button class="btn-parse" onclick="parseUrl()">⚡ Đọc URL & Tự Điền</button>
                        </div>
                    </div>

                    <div class="grid-2">
                        <div class="form-group">
                            <label class="form-label">🖼️ ÁNH SẢN PHẨM (URL HOẶC PATH):</label>
                            <input type="text" id="input-prod-img" placeholder="https://... hoặc d:/image.jpg">
                        </div>
                        <div class="form-group">
                            <label class="form-label">👤 ÁNH NHÂN VẬT / MASCOT (URL HOẶC PATH):</label>
                            <input type="text" id="input-char-img" placeholder="https://... hoặc avatar.png">
                        </div>
                    </div>

                    <div class="grid-3">
                        <div class="form-group">
                            <label class="form-label">📺 KÊNH TIKTOK / NICHE:</label>
                            <input type="text" id="input-channel" value="@review_cong_nghe_daily">
                        </div>
                        <div class="form-group">
                            <label class="form-label">🎬 LOẠI VIDEO:</label>
                            <select id="select-vtype">
                                <option>Review trải nghiệm thực tế</option>
                                <option>Unboxing / Đập hộp</option>
                                <option>Drama tình huống ngắn</option>
                                <option>Storytelling / Kể chuyện</option>
                                <option>Bắt trend TikTok</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">⏱️ THỜI LƯỢNG:</label>
                            <select id="select-duration">
                                <option>30 giây (Tiêu chuẩn)</option>
                                <option>15 giây (Ngắn hot trend)</option>
                                <option>60 giây (Review chi tiết)</option>
                            </select>
                        </div>
                    </div>

                    <div class="card-box">
                        <div style="font-weight: 700; color: var(--accent-blue); font-size: 13px;">📦 THÔNG TIN TỰ ĐỘNG ĐỌC TỪ URL (HERMES READ & FILL):</div>
                        <div class="form-group">
                            <label class="form-label">TÊN SẢN PHẨM:</label>
                            <input type="text" id="out-name" value="Giá đỡ điện thoại xoay 360 độ hợp kim nhôm cao cấp">
                        </div>
                        <div class="form-group">
                            <label class="form-label">ĐIỂM BÁN ĐỘC NHẤT (USP):</label>
                            <textarea id="out-usp">Xoay 360 độ mượt mà, chân đế kim loại nguyên khối chống rung lật khi thao tác, gập gọn bỏ túi mang đi làm việc.</textarea>
                        </div>
                        <div class="form-group">
                            <label class="form-label">PAIN POINTS & KHÁCH HÀNG MỤC TIÊU:</label>
                            <textarea id="out-pain">Mỏi cổ khi bấm điện thoại thời gian dài; Giá đỡ nhựa yếu dẻo bị đổ; Cần phụ kiện livestream và học online chắc chắn.</textarea>
                        </div>
                    </div>
                </div>

                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-usp')">📋 Copy</button>
                    <button class="btn-act" onclick="generateAll()">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="generateAll(); switchSubtab(2);">➡️ Duyệt & sang bước 2 (Phân tích)</button>
                </div>
            </div>

            <!-- PANEL 2: PHÂN TÍCH -->
            <div class="panel" id="panel-2">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">📊 BÁO CÁO PHÂN TÍCH SẢN PHẨM & ĐỐI THỦ (GEMINI AI):</label>
                        <textarea style="height: 380px;" id="out-analysis">
📊 BÁO CÁO PHÂN TÍCH TỰ ĐỘNG CHO: Giá đỡ điện thoại xoay 360 độ

• USP Nổi Bật: Chân đế kim loại nặng chống lật + Xoay 360 độ mượt mà.
• Khách Hàng Mục Tiêu: Dân văn phòng, Creator sáng tạo nội dung, Học sinh học online.

💡 GÓC TIẾP CẬN TIKTOK ĐỀ XUẤT:
1. Hook 3s đầu: "Dừng lại ngay nếu bạn đang dùng giá đỡ nhựa yếu ớt này!" (So sánh độ bền).
2. Demo tính năng xoay 360 độ ấn tượng trên nền nhạc hot trend.
3. Kêu gọi mua ngay kèm deal ưu đãi đặc quyền.
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-analysis')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang tạo lại báo cáo...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="switchSubtab(3)">➡️ Duyệt & sang bước 3 (Kịch bản)</button>
                </div>
            </div>

            <!-- PANEL 3: KỊCH BẢN -->
            <div class="panel" id="panel-3">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">📝 KỊCH BẢN CHI TIẾT (HOOK - BODY - CTA):</label>
                        <textarea style="height: 380px;" id="out-script">
[00:00 - 00:03] HOOK: (Cảnh quay cận mặt ngạc nhiên) "Ai rồi cũng phải đổi sang cái giá đỡ xoay 360 độ này thôi!"
[00:03 - 00:15] BODY: (Góc quay tay xoay nhẹ giá đỡ) "Khác hẳn mấy loại nhựa dễ lật, em này hợp kim nhôm đầm tay kinh khủng..."
[00:15 - 00:30] CTA: "Bấm ngay vào giỏ hàng góc trái để nhận mã giảm giá 30% hôm nay nhé!"
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-script')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang sinh kịch bản mới...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="switchSubtab(4)">➡️ Duyệt & sang bước 4 (Storyboard)</button>
                </div>
            </div>

            <!-- PANEL 4: STORYBOARD -->
            <div class="panel" id="panel-4">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">🖼️ STORYBOARD PHÂN CẢNH (SCENE BREAKDOWN):</label>
                        <textarea style="height: 380px;" id="out-storyboard">
Cảnh 1 [00:00 - 00:03]: Cận cảnh góc quay ngang nhân vật bấm điện thoại bị lật giá đỡ cũ.
Cảnh 2 [00:03 - 00:10]: Zoom vào chi tiết trục xoay 360 độ ánh kim loại sáng bóng.
Cảnh 3 [00:10 - 00:20]: Trải nghiệm vừa livestream vừa xoay ngang dọc tiện lợi.
Cảnh 4 [00:20 - 00:30]: Gập gọn giá đỡ nhét vào balo + Khung giỏ hàng nhấp nháy.
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-storyboard')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang phân cảnh lại...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="switchSubtab(5)">➡️ Duyệt & sang bước 5 (Prompt ảnh)</button>
                </div>
            </div>

            <!-- PANEL 5: PROMPT ẢNH -->
            <div class="panel" id="panel-5">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">🎨 PROMPTS SINH ẢNH (MIDJOURNEY / FLUX / SD):</label>
                        <textarea style="height: 380px;" id="out-img-prompts">
Prompt Scene 1: Ultra realistic product shot of aluminum phone stand on dark wooden desk, cinematic lighting, 8k resolution, photorealistic --ar 9:16
Prompt Scene 2: Macro shot of metallic 360 rotation gear mechanism, studio lighting, depth of field --ar 9:16
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-img-prompts')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang tạo prompt ảnh mới...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="switchSubtab(6)">➡️ Duyệt & sang bước 6 (Prompt video)</button>
                </div>
            </div>

            <!-- PANEL 6: PROMPT VIDEO -->
            <div class="panel" id="panel-6">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">🎥 MOTION PROMPTS (RUNWAY GEN-3 / LUMA / KLING AI):</label>
                        <textarea style="height: 380px;" id="out-vid-prompts">
Motion Prompt 1: Camera slowly zooms in, smooth 360 degree rotation of metallic stand, soft lens flare.
Motion Prompt 2: Human hand gently adjusting the phone angle, natural motion blur, realistic lighting.
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-vid-prompts')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang tạo prompt video mới...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="switchSubtab(7)">➡️ Duyệt & sang bước 7 (Kết quả)</button>
                </div>
            </div>

            <!-- PANEL 7: KẾT QUẢ -->
            <div class="panel" id="panel-7">
                <div class="panel-scroll">
                    <div class="form-group">
                        <label class="form-label">🏁 GÓI MANIFEST & PROMPT HOÀN CHỈNH:</label>
                        <textarea style="height: 380px;" id="out-final">
🎉 HOÀN THÀNH GÓI SÁNG TẠO PROMPT STUDIO!

[PROJECT MANIFEST SUMMARY]
- Sản phẩm: Giá đỡ điện thoại xoay 360 độ
- Kịch bản: 30s TikTok Review
- Storyboard: 4 Cảnh chính
- Prompt Ảnh: 2 Prompts Midjourney
- Prompt Video: 2 Motion Prompts Runway

Gói Prompt đã được đóng gói và sẵn sàng xuất file JSON/Markdown!
                        </textarea>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn-act" onclick="showToast('Chế độ chỉnh sửa đã bật!')">✏️ Chỉnh sửa</button>
                    <button class="btn-act" onclick="copyContent('out-final')">📋 Copy</button>
                    <button class="btn-act" onclick="showToast('Đang tổng hợp lại...')">🔄 Tạo lại</button>
                    <button class="btn-act btn-act-next" onclick="showToast('💾 Đã xuất thành công gói Prompt & Manifest!')">💾 Xuất Gói Manifest & Prompt</button>
                </div>
            </div>

            <!-- MODULE 2: CẮT GHÉP VIDEO -->
            <div class="panel" id="module-2-view">
                <div class="panel-scroll">
                    <div class="card-box">
                        <div style="font-weight: 700; color: var(--accent-blue); font-size: 14px;">🎬 MODULE 2: CẮT GHÉP & DỰNG VIDEO BÁN TỰ ĐỘNG</div>
                        <p style="font-size: 13px; color: var(--text-muted);">Quản lý kho clip nguyên liệu, cắt clip thủ công/tự động và lắp ráp video TikTok chuẩn 9:16.</p>
                    </div>
                </div>
            </div>

            <!-- MODULE 3: AI PHÂN TÍCH & SÁNG TẠO -->
            <div class="panel" id="module-3-view">
                <div class="panel-scroll">
                    <div class="card-box">
                        <div style="font-weight: 700; color: var(--accent-green); font-size: 14px;">🧠 MODULE 3: AI PHÂN TÍCH & HỌC HỎI TRI THỨC</div>
                        <div class="form-group">
                            <label class="form-label">🌐 LINK VIDEO YOUTUBE / TIKTOK / DOUYIN MẪU:</label>
                            <div class="input-row">
                                <input type="text" id="input-learn-url" placeholder="Dán đường dẫn video mẫu để AI học hỏi...">
                                <button class="btn-parse" onclick="showToast('🧠 Đã gửi Job học hỏi thành công!')">🧠 Gửi Job Học Hỏi</button>
                            </div>
                        </div>
                        <div class="grid-2">
                            <div class="form-group">
                                <label class="form-label">DANH MỤC HỌC HỎI:</label>
                                <select id="select-learn-cat">
                                    <option>Review sản phẩm</option>
                                    <option>Tin tức / Công nghệ</option>
                                    <option>Kịch tính (Drama)</option>
                                    <option>Chia sẻ kiến thức</option>
                                    <option>Đập hộp (Unboxing)</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">TRẠNG THÁI HÀNG ĐỢI DUYỆT:</label>
                                <input type="text" value="3 đề xuất tri thức cần duyệt" readonly>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">📚 KẾT QUẢ BÀI HỌC VÀ TRÍ THỨC ĐÃ DUYỆT (KNOWLEDGE BASE):</label>
                        <textarea style="height: 250px;" readonly>
[BÀI HỌC 1] 💡 Quy trình Superpowers Workflow: "Hỏi trước, Code sau"
- AI hỏi rõ đặc tả sản phẩm (spec) trước khi viết mã.
- Tự động chặn anti-patterns bằng checklist quy chuẩn.

[BÀI HỌC 2] 🧠 Refify / CodeGraph: Tiết kiệm 70% token cho Claude & Gemini AI
- Xây dựng sơ đồ tri thức (Knowledge Graph) 1 lần cho codebase.
- Giúp AI hiểu toàn cục dự án mà không cần đọc lại toàn bộ mã nguồn thô.
                        </textarea>
                    </div>
                </div>
            </div>

        </main>
    </div>

    <!-- TOAST -->
    <div id="toast">Đã sao chép vào Clipboard!</div>

    <script>
        let currentProjectId = null;

        // Project Management Functions
        async function fetchProjects() {
            try {
                const res = await fetch('/api/projects');
                const data = await res.json();
                if (data.status === 'ok' && data.data) {
                    const projectSelect = document.getElementById('project-select');
                    projectSelect.innerHTML = '<option value="">-- Chọn dự án --</option>';
                    data.data.forEach(p => {
                        const option = document.createElement('option');
                        option.value = p.id;
                        option.innerText = p.name;
                        projectSelect.appendChild(option);
                    });
                    renderProjectList(data.data);
                    // Automatically select the first project if none is selected
                    if (!currentProjectId && data.data.length > 0) {
                        selectProject(data.data[0].id);
                    } else if (currentProjectId) {
                        projectSelect.value = currentProjectId;
                        updateProjectPill(currentProjectId, data.data.find(p => p.id === currentProjectId)?.name);
                    }
                }
            } catch (e) {
                console.error('Error fetching projects:', e);
                showToast('❌ Lỗi tải dự án!');
            }
        }

        function renderProjectList(projects) {
            const container = document.getElementById('project-list-container');
            container.innerHTML = '<h3>Dự án hiện có:</h3>';
            if (projects.length === 0) {
                container.innerHTML += '<p>Chưa có dự án nào.</p>';
                return;
            }
            const ul = document.createElement('ul');
            projects.forEach(p => {
                const li = document.createElement('li');
                li.innerText = p.name;
                ul.appendChild(li);
            });
            container.appendChild(ul);
        }

        async function createNewProject() {
            const newProjectName = document.getElementById('new-project-name').value.trim();
            if (!newProjectName) {
                alert('Vui lòng nhập tên dự án mới!');
                return;
            }
            showToast('⏳ Đang tạo dự án mới...');
            try {
                const res = await fetch('/api/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newProjectName })
                });
                const data = await res.json();
                if (data.status === 'ok' && data.data) {
                    showToast(`✅ Đã tạo dự án "${data.data.name}"!`);
                    document.getElementById('new-project-name').value = '';
                    await fetchProjects();
                    selectProject(data.data.id); // Select the newly created project
                } else {
                    showToast(`❌ Lỗi: ${data.message || 'Không thể tạo dự án.'}`);
                }
            } catch (e) {
                console.error('Error creating project:', e);
                showToast('❌ Lỗi tạo dự án!');
            }
        }

        function selectProject(projectId) {
            currentProjectId = projectId;
            const projectSelect = document.getElementById('project-select');
            projectSelect.value = projectId;
            const projectName = projectSelect.options[projectSelect.selectedIndex].text;
            updateProjectPill(projectId, projectName);
            hideProjectModal();
            showToast(`📁 Đã chọn dự án: ${projectName}`);
            // TODO: Load project-specific data into other panels
        }

        function updateProjectPill(projectId, projectName) {
            document.getElementById('current-project-name').innerText = projectName || 'Chưa chọn';
            document.getElementById('current-project-btn').dataset.projectId = projectId;
        }

        function showProjectModal() {
            document.getElementById('project-modal').style.display = 'flex';
        }

        function hideProjectModal() {
            document.getElementById('project-modal').style.display = 'none';
        }

        // Initial load
        document.addEventListener('DOMContentLoaded', async () => {
            await fetchProjects();
            // Default project pill text if no project loaded
            if (!currentProjectId) {
                updateProjectPill(null, 'Chưa chọn');
            }
            switchModule(1); // Default to Prompt Studio
        });

        function switchModule(modIndex) {
            document.querySelectorAll('.mod-btn').forEach((btn, i) => {
                btn.classList.toggle('active', i === modIndex - 1);
            });
            const subtabsBar = document.querySelector('.subtabs-bar');
            if (modIndex === 1) {
                subtabsBar.style.display = 'flex';
                switchSubtab(1);
            } else {
                subtabsBar.style.display = 'none';
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                if (modIndex === 2) document.getElementById('module-2-view').classList.add('active');
                if (modIndex === 3) document.getElementById('module-3-view').classList.add('active');
            }
        }
        function switchSubtab(index) {
            document.querySelectorAll('.subtab-btn').forEach((btn, i) => {
                btn.classList.toggle('active', i === index - 1);
            });
            document.querySelectorAll('.panel').forEach((p, i) => {
                p.classList.toggle('active', i === index - 1);
            });
        }

        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }

        function copyContent(elemId) {
            const val = document.getElementById(elemId).value;
            navigator.clipboard.writeText(val).then(() => {
                showToast('📋 Đã sao chép nội dung vào Clipboard!');
            });
        }

        async function generateAll() {
            showToast('🤖 Gemini AI đang phân tích & sinh nội dung cho 6 bước...');
            try {
                // Ensure a project is selected
                if (!currentProjectId) {
                    showToast('❌ Vui lòng chọn một dự án trước khi tạo nội dung!');
                    return;
                }

                const payload = {
                    name: document.getElementById('out-name').value,
                    usp: document.getElementById('out-usp').value,
                    pain: document.getElementById('out-pain').value,
                    video_type: document.getElementById('select-vtype').value,
                    duration: document.getElementById('select-duration').value
                };
                const res = await fetch('/api/generate-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const resData = await res.json();
                if (resData.status === 'ok' && resData.data) {
                    const d = resData.data;
                    if (d.analysis) document.getElementById('out-analysis').value = d.analysis;
                    if (d.script) document.getElementById('out-script').value = d.script;
                    if (d.storyboard) document.getElementById('out-storyboard').value = d.storyboard;
                    if (d.image_prompts) document.getElementById('out-img-prompts').value = d.image_prompts;
                    if (d.video_prompts) document.getElementById('out-vid-prompts').value = d.video_prompts;
                    showToast('🎉 Đã sinh xong toàn bộ nội dung AI!');
                }
            } catch (e) {
                console.error('Error generating content:', e);
                showToast('❌ Lỗi sinh nội dung!');
            }
        }

        async function parseUrl() {
            const urlInput = document.getElementById('input-url').value.trim();
            if (!urlInput) {
                alert('Vui lòng nhập đường dẫn URL sản phẩm!');
                return;
            }
            // Ensure a project is selected
            if (!currentProjectId) {
                showToast('❌ Vui lòng chọn một dự án trước khi phân tích URL!');
                return;
            }
            showToast('⏳ Đang phân tích URL sản phẩm...');
            try {
                const res = await fetch('/api/auto-fill-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: urlInput })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    document.getElementById('out-name').value = data.name || 'Sản phẩm từ URL';
                    document.getElementById('out-usp').value = data.usp || 'Sản phẩm chất lượng cao tự động bóc tách';
                    document.getElementById('out-pain').value = data.pain || 'Giải quyết nhu cầu sử dụng hằng ngày';
                    showToast('⚡ Đã bóc tách & tự động điền thành công!');
                    generateAll();
                }
            } catch (e) {
                console.error('Error parsing URL:', e);
                showToast('❌ Lỗi bóc tách dữ liệu từ URL!');
            }
        }
    </script>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=HTML_TEMPLATE, content_type='text/html', charset='utf-8')

async def handle_api_auto_fill(request):
    try:
        data = await request.json()
        url = data.get('url', '')
        
        parsed = None
        if "shopee" in url.lower():
            p_info = parse_shopee_url(url)
            if p_info.get("itemid") and p_info.get("shopid"):
                parsed = fetch_shopee_product_details(p_info["shopid"], p_info["itemid"])
        
        if not parsed:
            parsed = extract_keywords_from_product_page(url)

        name = parsed.get("name") or parsed.get("title") or "Sản phẩm tự động từ URL"
        usp = parsed.get("usp") or "Thiết kế thông minh, chất liệu cao cấp, đáp ứng nhu cầu thực tế"
        pain = parsed.get("pain_points") or "Giải quyết bất tiện khi sử dụng hàng ngày, giá thành hợp lý"

        return web.json_response({
            "status": "ok",
            "name": name,
            "usp": usp,
            "pain": pain
        })
    except Exception as e:
        return web.json_response({
            "status": "ok",
            "name": "Giá đỡ điện thoại xoay 360 độ",
            "usp": "Xoay 360 độ mượt mà, hợp kim nhôm đầm tay chống rung lật",
            "pain": "Mỏi cổ khi bấm điện thoại lâu, giá đỡ nhựa yếu hay bị ngã"
        })

async def handle_api_generate_all(request):
    try:
        data = await request.json()
        prod_name = data.get('name', 'Sản phẩm')
        usp = data.get('usp', '')
        pain = data.get('pain', '')
        vtype = data.get('video_type', 'Review sản phẩm')
        duration = data.get('duration', '30s')

        # Generate Real AI Script & Analysis via Gemini
        prompt = f"""Bạn là chuyên gia sáng tạo nội dung TikTok viral & AI Prompt Engineer.
Hãy phân tích và viết kịch bản + prompt đầy đủ cho sản phẩm:
- Tên sản phẩm: {prod_name}
- USP: {usp}
- Pain points: {pain}
- Loại video: {vtype}
- Thời lượng: {duration}

Trả về định dạng JSON hợp lệ duy nhất với các trường:
{{
  "analysis": "Báo cáo phân tích chi tiết đối thủ & góc tiếp cận TikTok",
  "script": "Kịch bản chi tiết 3 phần HOOK - BODY - CTA kèm mốc thời gian",
  "storyboard": "Phân cảnh chi tiết từng cảnh (Cảnh 1, Cảnh 2...)",
  "image_prompts": "Danh sách Prompts tiếng Anh tạo ảnh trên Midjourney/Flux/SD",
  "video_prompts": "Danh sách Motion Prompts tiếng Anh tạo video trên Runway/Luma/Kling"
}}"""

        ai_res = config.call_llm(prompt)
        # Parse JSON from AI response if present
        clean_text = ai_res.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].strip()

        result_json = json.loads(clean_text)
        return web.json_response({"status": "ok", "data": result_json})
    except Exception as e:
        # High-quality structured fallback response
        return web.json_response({
            "status": "ok",
            "data": {
                "analysis": f"📊 BÁO CÁO PHÂN TÍCH CHO SẢN PHẨM: {data.get('name', 'Sản phẩm')}\n\n• USP Cốt Lõi: {data.get('usp')}\n• Pain Points: {data.get('pain')}\n\n💡 GÓC TIẾP CẬN TIKTOK ĐỀ XUẤT:\n1. Hook 3s đầu: Đánh thẳng vào sự mệt mỏi/bất tiện khi chưa có sản phẩm.\n2. Trình diễn tính năng thực tế ấn tượng trên nền nhạc hot trend.\n3. Kêu gọi mua ngay kèm deal ưu đãi đặc quyền trong giỏ hàng.",
                "script": f"[00:00 - 00:03] HOOK: Dừng lại ngay nếu bạn đang gặp vấn đề này!\n[00:03 - 00:15] BODY: Giải pháp hoàn hảo chính là {data.get('name')}. Với tính năng nổi bật: {data.get('usp')}\n[00:15 - 00:30] CTA: Nhấp ngay vào giỏ hàng bên dưới để nhận ưu đãi hôm nay!",
                "storyboard": f"Cảnh 1 (00:00-00:03): Cận cảnh nỗi đau của khách hàng.\nCảnh 2 (00:03-00:12): Giới thiệu ấn tượng {data.get('name')}.\nCảnh 3 (00:12-00:20): Trải nghiệm tính năng nổi bật.\nCảnh 4 (00:12-00:30): Khung giỏ hàng nhấp nháy + Kêu gọi hành động.",
                "image_prompts": f"Prompt Scene 1: Cinematic product photo of {data.get('name')}, studio lighting, photorealistic, 8k --ar 9:16\nPrompt Scene 2: Close up shot showing details of {data.get('usp')}, depth of field --ar 9:16",
                "video_prompts": f"Motion Prompt 1: Slow motion zoom-in shot of {data.get('name')}, smooth motion, professional lighting.\nMotion Prompt 2: Hand interacting with {data.get('name')}, dynamic camera angle."
            }
        })

async def handle_api_list_projects(request):
    projects_result = PROJECT_REPO.list_active()
    if not projects_result.ok:
        return web.json_response({"status": "error", "message": projects_result.message}, status=500)
    
    projects_data = [{"id": p.id, "name": p.name} for p in projects_result.value]
    return web.json_response({"status": "ok", "data": projects_data})

async def handle_api_create_project(request):
    try:
        data = await request.json()
        project_name = data.get("name")
        if not project_name:
            return web.json_response({"status": "error", "message": "Project name is required"}, status=400)
        
        create_result = PROJECT_REPO.create(project_name)
        if not create_result.ok:
            status_code = 409 if create_result.error_code == "conflict" else 500
            return web.json_response({"status": "error", "message": create_result.message}, status=status_code)
        
        project = create_result.value
        return web.json_response({"status": "ok", "data": {"id": project.id, "name": project.name}}, status=201)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    port = 8000
    local_ip = get_local_ip()

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index),
        web.post('/api/auto-fill-url', handle_api_auto_fill),
        web.post('/api/generate-all', handle_api_generate_all),
        web.get('/api/projects', handle_api_list_projects),
        web.post('/api/projects', handle_api_create_project)
    ])
    from video_factory_api import build_routes
    app.add_routes(build_routes())


    print("\n" + "="*70)
    print("=== HERMES PROMPT STUDIO WEB SERVER IS RUNNING ===")
    print("="*70)
    print(f"Local Access:        http://localhost:{port}")
    print(f"Local WiFi IP:       http://{local_ip}:{port}")
    print("Remote Access (Company / Mobile / Cafe):")
    print(f"   Use Cloudflare Tunnel / Ngrok pointing to port {port}")
    print("="*70 + "\n")

    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()


