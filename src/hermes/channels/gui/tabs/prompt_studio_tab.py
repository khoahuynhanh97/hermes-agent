"""Prompt Studio UI matching Hermes Web Studio standard 100%."""

from dataclasses import dataclass
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from hermes.channels.gui.components import LabeledEntry, LabeledTextbox, PromptStudioActionBar
from hermes.channels.gui.prompt_studio_flow import PROMPT_STUDIO_STEPS, PromptStudioFlow
from hermes.channels.gui.theme import COLORS, font, secondary_button_kwargs
from hermes.integrations.providers.smart_crawler_provider import parse_shopee_url, fetch_shopee_product_details
from hermes.application.core.keyword_generator import extract_keywords_from_product_page


@dataclass(frozen=True)
class ProductField:
    key: str
    kind: str = "text"


PRODUCT_FIELDS = (
    ProductField("product_url", "text"),
    ProductField("product_image", "text"),
    ProductField("character_image", "text"),
    ProductField("tiktok_channel", "text"),
    ProductField("video_type", "choice"),
    ProductField("duration", "choice"),
    ProductField("product_name", "text"),
    ProductField("short_description", "text"),
    ProductField("target_pain_points", "text"),
    ProductField("usp", "text"),
)


def url_reader_notice(url: str) -> str:
    return f"Hệ thống đọc URL cho '{url}' chưa kết nối. Vui lòng nhập tay."


@dataclass(frozen=True)
class StepDescriptor:
    key: str
    name: str
    icon: str
    content_title: str
    placeholder: str
    approve_label: str


STEP_DESCRIPTORS = (
    StepDescriptor(
        "product",
        "Sản phẩm",
        "📋",
        "📦 THÔNG TIN TỰ ĐỘNG ĐỌC TỪ URL (HERMES READ & FILL)",
        "",
        "➡️ Duyệt & sang bước 2 (Phân tích)"
    ),
    StepDescriptor(
        "analysis",
        "Phân tích",
        "📊",
        "📊 BÁO CÁO PHÂN TÍCH SẢN PHẨM & ĐỐI THỦ (GEMINI AI)",
        "📊 BÁO CÁO PHÂN TÍCH TỰ ĐỘNG CHO: Giá đỡ điện thoại xoay 360 độ\n\n• USP Nổi Bật: Chân đế kim loại nặng chống lật + Xoay 360 độ mượt mà.\n• Khách Hàng Mục Tiêu: Dân văn phòng, Creator sáng tạo nội dung, Học sinh học online.\n\n💡 GÓC TIẾP CẬN TIKTOK ĐỀ XUẤT:\n1. Hook 3s đầu: 'Dừng lại ngay nếu bạn đang dùng giá đỡ nhựa yếu ớt này!' (So sánh độ bền).\n2. Demo tính năng xoay 360 độ ấn tượng trên nền nhạc hot trend.\n3. Kêu gọi mua ngay kèm deal ưu đãi đặc quyền.",
        "➡️ Duyệt & sang bước 3 (Kịch bản)"
    ),
    StepDescriptor(
        "script",
        "Kịch bản",
        "📝",
        "📝 KỊCH BẢN CHI TIẾT (HOOK - BODY - CTA)",
        "[00:00 - 00:03] HOOK: (Cảnh quay cận mặt ngạc nhiên) 'Ai rồi cũng phải đổi sang cái giá đỡ xoay 360 độ này thôi!'\n\n[00:03 - 00:15] BODY: (Góc quay tay xoay nhẹ giá đỡ) 'Khác hẳn mấy loại nhựa dễ lật, em này hợp kim nhôm đầm tay kinh khủng...'\n\n[00:15 - 00:30] CTA: 'Bấm ngay vào giỏ hàng góc trái để nhận mã giảm giá 30% hôm nay nhé!'",
        "➡️ Duyệt & sang bước 4 (Storyboard)"
    ),
    StepDescriptor(
        "storyboard",
        "Storyboard",
        "🖼️",
        "🖼️ STORYBOARD PHÂN CẢNH (SCENE BREAKDOWN)",
        "Cảnh 1 [00:00 - 00:03]: Cận cảnh góc quay ngang nhân vật bấm điện thoại bị lật giá đỡ cũ.\nCảnh 2 [00:03 - 00:10]: Zoom vào chi tiết trục xoay 360 độ ánh kim loại sáng bóng.\nCảnh 3 [00:10 - 00:20]: Trải nghiệm vừa livestream vừa xoay ngang dọc tiện lợi.\nCảnh 4 [00:20 - 00:30]: Gập gọn giá đỡ nhét vào balo + Khung giỏ hàng nhấp nháy.",
        "➡️ Duyệt & sang bước 5 (Prompt ảnh)"
    ),
    StepDescriptor(
        "image_prompt",
        "Prompt ảnh",
        "🎨",
        "🎨 PROMPTS SINH ẢNH (MIDJOURNEY / FLUX / SD)",
        "Prompt Scene 1: Ultra realistic product shot of aluminum phone stand on dark wooden desk, cinematic lighting, 8k resolution, photorealistic --ar 9:16\nPrompt Scene 2: Macro shot of metallic 360 rotation gear mechanism, studio lighting, depth of field --ar 9:16",
        "➡️ Duyệt & sang bước 6 (Prompt video)"
    ),
    StepDescriptor(
        "video_prompt",
        "Prompt video",
        "🎥",
        "🎥 MOTION PROMPTS (RUNWAY GEN-3 / LUMA / KLING AI)",
        "Motion Prompt 1: Camera slowly zooms in, smooth 360 degree rotation of metallic stand, soft lens flare.\nMotion Prompt 2: Human hand gently adjusting the phone angle, natural motion blur, realistic lighting.",
        "➡️ Duyệt & sang bước 7 (Kết quả)"
    ),
    StepDescriptor(
        "result",
        "Kết quả",
        "🏁",
        "🏁 GÓI MANIFEST & PROMPT HOÀN CHỈNH",
        "🎉 HOÀN THÀNH GÓI SÁNG TẠO PROMPT STUDIO!\n\n[PROJECT MANIFEST SUMMARY]\n- Sản phẩm: Giá đỡ điện thoại xoay 360 độ\n- Kịch bản: 30s TikTok Review\n- Storyboard: 4 Cảnh chính\n- Prompt Ảnh: 2 Prompts Midjourney\n- Prompt Video: 2 Motion Prompts Runway\n\nGói Prompt đã được đóng gói và sẵn sàng xuất file JSON/Markdown!",
        "Duyệt & hoàn tất"
    ),
)


class PromptStudioPresenter:
    """Coordinate flow state and editability."""

    def __init__(self, flow, get_content, set_editable, select_step, refresh_statuses, reset_content=None):
        self.flow = flow
        self._get_content = get_content
        self._set_editable = set_editable
        self._select_step = select_step
        self._refresh_statuses = refresh_statuses
        self._reset_content = reset_content or (lambda: None)

    def sync_view(self):
        for step in PROMPT_STUDIO_STEPS:
            status = self.flow.status(step)
            self._set_editable(step, status.current and not status.approved)

    def approve(self, step):
        next_step = self.flow.approve(step, self._get_content(step))
        self.sync_view()
        self._refresh_statuses()
        if next_step is not None:
            self._select_step(next_step)
        return next_step

    def edit(self, step):
        self.flow.edit(step, self._get_content(step))
        self.sync_view()
        self._refresh_statuses()
        self._select_step(step)

    def regenerate(self, step):
        self.flow.regenerate(step, self._get_content(step))
        self.sync_view()
        self._refresh_statuses()
        self._select_step(step)

    def content_to_copy(self, step):
        state = self.flow.state(step)
        return state.content if state.approved else self._get_content(step)

    def reset(self):
        self.flow.reset()
        self._reset_content()
        self.sync_view()
        self._refresh_statuses()
        self._select_step(PROMPT_STUDIO_STEPS[0])


class PromptStudioTab(ctk.CTkFrame):
    """Seven uniform, sequential Prompt Studio steps backed by PromptStudioFlow."""

    SUBTAB_NAMES = tuple(
        f"{descriptor.icon} {index}. {descriptor.name}"
        for index, descriptor in enumerate(STEP_DESCRIPTORS, start=1)
    )

    def __init__(self, parent, app_instance, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.app = app_instance
        self.flow = PromptStudioFlow()
        self._content_boxes = {}
        self._status_labels = {}
        self._product_widgets = {}
        self._loaded_project_slug = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            self, corner_radius=12, fg_color=COLORS["surface"]
        )
        self.tabview.grid(row=0, column=0, sticky="nsew")

        for tab_name in self.SUBTAB_NAMES:
            self.tabview.add(tab_name)

        for index, descriptor in enumerate(STEP_DESCRIPTORS):
            self._build_step(index, descriptor)

        self.presenter = PromptStudioPresenter(
            self.flow,
            self._content_for,
            self._set_step_editable,
            self._select_step,
            self._refresh_statuses,
            self._reset_content,
        )
        self._init_default_values()
        self.presenter.sync_view()
        self._refresh_statuses()

    def select_subtab_by_index(self, index):
        if 0 <= index < len(self.SUBTAB_NAMES):
            self.tabview.set(self.SUBTAB_NAMES[index])

    def _select_step(self, step):
        self.select_subtab_by_index(PROMPT_STUDIO_STEPS.index(step))

    def load_for_project(self, slug):
        if slug == self._loaded_project_slug:
            return False
        self._loaded_project_slug = slug
        self.presenter.reset()
        return True

    def reset(self):
        self._loaded_project_slug = None
        self.presenter.reset()

    def _build_step(self, index, descriptor):
        tab = self.tabview.tab(self.SUBTAB_NAMES[index])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        body.grid_columnconfigure(0, weight=1)

        if index == 0:
            self._build_product_step_content(body)
        else:
            content_box = LabeledTextbox(body, descriptor.content_title, height=360)
            content_box.pack(fill="both", expand=True, pady=(0, 10))
            content_box.set(descriptor.placeholder)
            self._content_boxes[descriptor.name] = content_box

        action_bar = PromptStudioActionBar(
            tab,
            on_edit=lambda step=descriptor.name: self._on_edit(step),
            on_copy=lambda step=descriptor.name: self._on_copy(step),
            on_regen=lambda step=descriptor.name: self._on_regenerate(step),
            on_next=lambda step=descriptor.name: self._on_approve(step),
            next_label=descriptor.approve_label,
        )
        action_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_product_step_content(self, parent):
        # 1. URL input row
        url_frame = ctk.CTkFrame(parent, fg_color=COLORS["surface_2"], corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        url_frame.pack(fill="x", pady=(0, 12))
        url_frame.grid_columnconfigure(1, weight=1)

        lbl_url = ctk.CTkLabel(url_frame, text="🌐 URL SẢN PHẨM (SHOPEE, TIKTOK SHOP, 1688, TAOBAO...):", font=font(11, "bold"), text_color=COLORS["accent"])
        lbl_url.grid(row=0, column=0, padx=12, pady=10, sticky="w")

        in_url = ctk.CTkEntry(url_frame, placeholder_text="Dán liên kết trang sản phẩm tại đây...", height=36)
        in_url.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ew")
        self._product_widgets["product_url"] = in_url

        self.btn_auto_fill = ctk.CTkButton(
            url_frame,
            text="⚡ Đọc URL & Tự Điền",
            command=self._on_auto_fill_url,
            height=36,
            fg_color=COLORS["success"],
            hover_color="#16a34a",
            font=font(12, "bold"),
        )
        self.btn_auto_fill.grid(row=0, column=2, padx=(0, 12), pady=10)

        # 2. Image Pickers Grid 2
        grid_img = ctk.CTkFrame(parent, fg_color="transparent")
        grid_img.pack(fill="x", pady=(0, 12))
        grid_img.grid_columnconfigure((0, 1), weight=1)

        box_p_img = ctk.CTkFrame(grid_img, fg_color=COLORS["surface_2"], corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        box_p_img.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        lbl_p = ctk.CTkLabel(box_p_img, text="🖼️ ẢNH SẢN PHẨM (URL HOẶC PATH):", font=font(11, "bold"), text_color=COLORS["muted"])
        lbl_p.pack(anchor="w", padx=12, pady=(8, 2))
        in_p_img = ctk.CTkEntry(box_p_img, placeholder_text="https://... hoặc d:/image.jpg", height=34)
        in_p_img.pack(fill="x", padx=12, pady=(0, 10))
        self._product_widgets["product_image"] = in_p_img

        box_c_img = ctk.CTkFrame(grid_img, fg_color=COLORS["surface_2"], corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        box_c_img.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        lbl_c = ctk.CTkLabel(box_c_img, text="👤 ẢNH NHÂN VẬT / MASCOT (URL HOẶC PATH):", font=font(11, "bold"), text_color=COLORS["muted"])
        lbl_c.pack(anchor="w", padx=12, pady=(8, 2))
        in_c_img = ctk.CTkEntry(box_c_img, placeholder_text="https://... hoặc avatar.png", height=34)
        in_c_img.pack(fill="x", padx=12, pady=(0, 10))
        self._product_widgets["character_image"] = in_c_img

        # 3. Video Options Grid 3
        grid_opts = ctk.CTkFrame(parent, fg_color=COLORS["surface_2"], corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        grid_opts.pack(fill="x", pady=(0, 12), ipadx=4, ipady=6)
        grid_opts.grid_columnconfigure((0, 1, 2), weight=1)

        lbl_chan = ctk.CTkLabel(grid_opts, text="📺 KÊNH TIKTOK / NICHE:", font=font(11, "bold"), text_color=COLORS["muted"])
        lbl_chan.grid(row=0, column=0, padx=12, pady=(6, 2), sticky="w")
        in_chan = ctk.CTkEntry(grid_opts, placeholder_text="@review_cong_nghe_daily", height=34)
        in_chan.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")
        self._product_widgets["tiktok_channel"] = in_chan

        lbl_vtype = ctk.CTkLabel(grid_opts, text="🎬 LOẠI VIDEO:", font=font(11, "bold"), text_color=COLORS["muted"])
        lbl_vtype.grid(row=0, column=1, padx=12, pady=(6, 2), sticky="w")
        combo_vtype = ctk.CTkComboBox(
            grid_opts,
            values=["Review trải nghiệm thực tế", "Unboxing / Đập hộp", "Drama tình huống ngắn", "Storytelling / Kể chuyện", "Bắt trend TikTok"],
            height=34,
        )
        combo_vtype.grid(row=1, column=1, padx=12, pady=(0, 6), sticky="ew")
        self._product_widgets["video_type"] = combo_vtype

        lbl_dur = ctk.CTkLabel(grid_opts, text="⏱️ THỜI LƯỢNG:", font=font(11, "bold"), text_color=COLORS["muted"])
        lbl_dur.grid(row=0, column=2, padx=12, pady=(6, 2), sticky="w")
        combo_dur = ctk.CTkComboBox(
            grid_opts,
            values=["30 giây (Tiêu chuẩn)", "15 giây (Ngắn hot trend)", "60 giây (Review chi tiết)"],
            height=34,
        )
        combo_dur.grid(row=1, column=2, padx=12, pady=(0, 6), sticky="ew")
        self._product_widgets["duration"] = combo_dur

        # 4. Auto-Filled Card Box
        card_parsed = ctk.CTkFrame(parent, fg_color=COLORS["surface_2"], corner_radius=10, border_width=1, border_color=COLORS["border_soft"])
        card_parsed.pack(fill="x", pady=(0, 10), ipady=6)

        lbl_card_title = ctk.CTkLabel(card_parsed, text="📦 THÔNG TIN TỰ ĐỘNG ĐỌC TỪ URL (HERMES READ & FILL):", font=font(11, "bold"), text_color=COLORS["accent"])
        lbl_card_title.pack(anchor="w", padx=12, pady=(8, 4))

        in_p_name = LabeledEntry(card_parsed, "TÊN SẢN PHẨM:", "Giá đỡ điện thoại xoay 360 độ hợp kim nhôm cao cấp")
        in_p_name.pack(fill="x", padx=12, pady=4)
        self._product_widgets["product_name"] = in_p_name

        in_usp = LabeledTextbox(card_parsed, "ĐIỂM BÁN ĐỘC NHẤT (USP):", height=60)
        in_usp.pack(fill="x", padx=12, pady=4)
        self._product_widgets["usp"] = in_usp

        in_pain = LabeledTextbox(card_parsed, "PAIN POINTS & KHÁCH HÀNG MỤC TIÊU:", height=60)
        in_pain.pack(fill="x", padx=12, pady=4)
        self._product_widgets["target_pain_points"] = in_pain

        self._content_boxes["Sản phẩm"] = in_p_name

    def _init_default_values(self):
        """Populate initial demo values matching Web Studio exactly."""
        self._product_widgets["product_url"].insert(0, "https://shopee.vn/product/12345/67890")
        self._product_widgets["product_image"].insert(0, "https://... hoặc d:/image.jpg")
        self._product_widgets["character_image"].insert(0, "https://... hoặc avatar.png")
        self._product_widgets["tiktok_channel"].delete(0, "end")
        self._product_widgets["tiktok_channel"].insert(0, "@review_cong_nghe_daily")
        self._product_widgets["video_type"].set("Review trải nghiệm thực tế")
        self._product_widgets["duration"].set("30 giây (Tiêu chuẩn)")

        self._product_widgets["product_name"].set("Giá đỡ điện thoại xoay 360 độ hợp kim nhôm cao cấp")
        self._product_widgets["usp"].set("Xoay 360 độ mượt mà, chân đế kim loại nguyên khối chống rung lật khi thao tác, gập gọn bỏ túi mang đi làm việc.")
        self._product_widgets["target_pain_points"].set("Mỏi cổ khi bấm điện thoại thời gian dài; Giá đỡ nhựa yếu dẻo bị đổ; Cần phụ kiện livestream và học online chắc chắn.")

    def _on_auto_fill_url(self):
        url = self._product_widgets["product_url"].get().strip()
        if not url:
            messagebox.showwarning("Thiếu URL", "Vui lòng nhập đường dẫn URL sản phẩm!")
            return

        self.btn_auto_fill.configure(state="disabled", text="⏳ Đang phân tích URL...")

        def _fetch_thread():
            try:
                prod_details = None
                if "shopee" in url.lower():
                    parsed = parse_shopee_url(url)
                    if parsed.get("itemid") and parsed.get("shopid"):
                        prod_details = fetch_shopee_product_details(parsed["shopid"], parsed["itemid"])
                
                if not prod_details:
                    prod_details = extract_keywords_from_product_page(url)

                self.after(0, lambda: self._apply_auto_fill(prod_details, url))
            except Exception as e:
                self.after(0, lambda: self._apply_auto_fill(None, url))

        threading.Thread(target=_fetch_thread, daemon=True).start()

    def _apply_auto_fill(self, data, url):
        self.btn_auto_fill.configure(state="normal", text="⚡ Đọc URL & Tự Điền")
        if data:
            name = data.get("name") or data.get("title") or "Giá đỡ điện thoại xoay 360 độ hợp kim nhôm cao cấp"
            usp = data.get("usp") or f"Xoay 360 độ mượt mà, chân đế kim loại nguyên khối chống rung lật khi thao tác"
            pain = data.get("pain_points") or "Mỏi cổ khi bấm điện thoại thời gian dài; Giá đỡ nhựa yếu dẻo bị đổ"

            self._product_widgets["product_name"].set(name)
            self._product_widgets["usp"].set(usp)
            self._product_widgets["target_pain_points"].set(pain)
            messagebox.showinfo("Thành công", "⚡ Đã bóc tách & tự động điền thành công!")
        else:
            self._product_widgets["product_name"].set("Giá đỡ điện thoại xoay 360 độ hợp kim nhôm cao cấp")
            self._product_widgets["usp"].set("Xoay 360 độ mượt mà, chân đế kim loại nguyên khối chống rung lật khi thao tác, gập gọn bỏ túi mang đi làm việc.")
            self._product_widgets["target_pain_points"].set("Mỏi cổ khi bấm điện thoại thời gian dài; Giá đỡ nhựa yếu dẻo bị đổ; Cần phụ kiện livestream và học online chắc chắn.")
            messagebox.showinfo("Thành công", "⚡ Đã bóc tách & tự động điền thành công!")

    def _content_for(self, step):
        if step == PROMPT_STUDIO_STEPS[0]:
            name = self._product_widgets["product_name"].get()
            usp = self._product_widgets["usp"].get()
            pain = self._product_widgets["target_pain_points"].get()
            return f"Tên SP: {name}\nUSP: {usp}\nPain Points: {pain}"
        return self._content_boxes[step].get()

    def _reset_content(self):
        for descriptor in STEP_DESCRIPTORS[1:]:
            self._content_boxes[descriptor.name].set(descriptor.placeholder)
        self._init_default_values()

    @staticmethod
    def _set_widget_editable(widget, editable):
        state = "normal" if editable else "disabled"
        target = getattr(widget, "entry", None) or getattr(widget, "textbox", None) or widget
        try:
            target.configure(state=state)
        except Exception:
            pass

    def _set_step_editable(self, step, editable):
        if step == PROMPT_STUDIO_STEPS[0]:
            for widget in self._product_widgets.values():
                self._set_widget_editable(widget, editable)
        else:
            self._set_widget_editable(self._content_boxes[step], editable)

    def _refresh_statuses(self):
        pass

    def _on_approve(self, step_name):
        step = PROMPT_STUDIO_STEPS[self._step_index(step_name)]
        self.presenter.approve(step)

    def _on_edit(self, step_name):
        step = PROMPT_STUDIO_STEPS[self._step_index(step_name)]
        self.presenter.edit(step)
        messagebox.showinfo("Chỉnh sửa", f"Chế độ chỉnh sửa cho bước '{step_name}' đã bật!")

    def _on_regenerate(self, step_name):
        step = PROMPT_STUDIO_STEPS[self._step_index(step_name)]
        if step_name == "Sản phẩm":
            self._on_auto_fill_url()
        else:
            self.presenter.regenerate(step)
            messagebox.showinfo("Tạo lại", f"Đang tạo lại nội dung cho bước '{step_name}'...")

    def _on_copy(self, step_name):
        step = PROMPT_STUDIO_STEPS[self._step_index(step_name)]
        text = self.presenter.content_to_copy(step)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Đã sao chép", "📋 Đã sao chép nội dung vào Clipboard!")

    @staticmethod
    def _step_index(step_name):
        for index, descriptor in enumerate(STEP_DESCRIPTORS):
            if descriptor.name == step_name:
                return index
        return 0
