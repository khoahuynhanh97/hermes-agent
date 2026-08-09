# Nghiên cứu prompt pipeline video AI ngắn cho TikTok affiliate

Ngày nghiên cứu: 2026-07-30

## Phạm vi và phương pháp

Báo cáo này chỉ dùng nguồn sơ cấp: TikTok Creative Center/Business Help Center/Support, tài liệu chính thức của Google Cloud (Imagen/Veo), Runway, Luma AI và Adobe Firefly. Các khuyến nghị có nhãn **Suy luận triển khai** là kết luận kỹ thuật rút ra từ các nguồn, không phải quy định nguyên văn của nền tảng.

## Kết luận điều hành

1. Pipeline nên biểu diễn nội dung theo `hook -> body -> close`, nhưng không nên cố định mọi video thành bốn cảnh 8 giây. TikTok coi sáu giây đầu là vùng quyết định sự chú ý, khuyên đưa value proposition vào sớm và kết thúc bằng CTA rõ; một checklist chính thức khuyến nghị video 9-15 giây, trong khi thông số In-Feed hiện tại cho phép nhiều độ dài hơn. Vì vậy tổng thời lượng và số cảnh phải là tham số theo mục tiêu, không phải hằng số. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf), [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf), [In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB))
2. Mốc "hook trong 2 giây" có thể giữ như một ràng buộc nội bộ nghiêm ngặt, nhưng bằng chứng TikTok chính thức được tìm thấy nói rộng hơn: ba đến sáu giây đầu hoặc sáu giây đầu là quan trọng. **Suy luận triển khai:** đặt `hook_visible_by_s <= 2`, đồng thời yêu cầu value proposition hoàn chỉnh trước giây thứ 6. ([Creative Starter Pack](https://ads.tiktok.com/business/library/AUNZ_Creative_Starter_Pack_TakeItToTikTok.pdf), [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en))
3. TikTok khuyến nghị cấu trúc hook-body-close, đưa sản phẩm/brand vào tự nhiên xuyên suốt, giữ thông điệp chính gắn với selling point và kết thúc bằng một hành động cụ thể. **Suy luận triển khai:** mỗi concept cần một `single_value_proposition`, một `proof_or_demo`, và một `cta_action`; không cho phép nhiều CTA cạnh tranh trong cùng bản dựng ngắn. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf), [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en))
4. Safe zone không phải một bộ tọa độ cố định dùng cho mọi video: nó thay đổi theo tỉ lệ khung hình, độ dài caption, anchor và add-on; TikTok yêu cầu dùng đúng file safe-zone và kiểm tra bằng Preview Tool. **Suy luận triển khai:** prompt chỉ nên yêu cầu "critical subject/product/text inside provider safe zone"; bước render phải áp overlay/mask theo placement thực tế và có bước preview QA. ([In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB), [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en))
5. Với image-to-video, ảnh đầu vào đã định nghĩa chủ thể, bố cục, ánh sáng và phong cách; prompt chuyển động nên tập trung vào camera motion, subject action, environmental motion, hướng, tốc độ và timing. Việc mô tả lại dày đặc ngoại hình có thể làm giảm chuyển động hoặc tạo kết quả ngoài ý muốn. ([Runway Image-to-Video Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide), [Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice))
6. Sáu keyframe văn bản ở các mốc đều nhau không phải abstraction chung của các model phổ biến. Veo và Luma hỗ trợ ảnh đầu/cuối; Runway keyframe khuyên ảnh phải gần nhau về chủ thể, cảnh và style, đồng thời prompt chỉ mô tả chuyển động nối giữa các khung. **Suy luận triển khai:** schema phải phân biệt `story_beats` với `provider_keyframes`; chỉ materialize first/middle/last frame khi adapter của model hỗ trợ. ([Veo first/last frames](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-first-and-last-frames), [Luma video API](https://docs.lumalabs.ai/ue/docs/video-generation), [Runway Keyframes](https://help.runwayml.com/hc/en-us/articles/34170748696595-Creating-with-Keyframes-on-Gen-3))
7. Mỗi clip sinh video nên là một cảnh có một hành động chính và một chuyển động camera chính. Runway cảnh báo rằng ép nhiều thay đổi cảnh, hành động và style theo từng giây có thể tạo chỉ dẫn mâu thuẫn; Google cũng khuyên video ngắn tập trung vào một cảnh. ([Runway Gen-4 Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide), [Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice))
8. Tính nhất quán nên được quản lý bằng dữ liệu bất biến và reference assets, không chỉ bằng tính từ như "cinematic, hyper-realistic". Google khuyên lặp nguyên vẹn mô tả nhân vật và dùng cùng seed giữa các cảnh; Firefly cho phép reference riêng cho composition và style, với mức adherence điều chỉnh được. ([Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice), [Firefly composition reference](https://helpx.adobe.com/firefly/web/work-with-images/generate-images/match-image-composition-to-reference-image.html), [Firefly style reference](https://helpx.adobe.com/uk/firefly/how-to/generate-image-using-reference-image.html))
9. Affiliate là commercial content khi có lợi ích tài chính, brand mention hoặc product recommendation/CTA; TikTok yêu cầu bật Commercial Content Disclosure. Với nội dung AI hoàn toàn hoặc chỉnh sửa đáng kể, phải thêm AIGC label/disclaimer; thiếu disclosure có thể làm video bị hạn chế phân phối hoặc quảng cáo bị từ chối. ([Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en), [Promoting a brand/product/service](https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/promoting-a-brand-product-or-service), [Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content))
10. Prompt và QA phải chặn claim tuyệt đối, kết quả phóng đại, before/after gây hiểu sai, giá/discount không khớp landing page, CTA giả và sản phẩm/brand khác landing page. Âm nhạc thương mại nên lấy từ Commercial Music Library hoặc nguồn đã có quyền sử dụng. ([Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content), [Ad format and functionality](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en), [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en))

## 1. Hướng dẫn sáng tạo từ TikTok

### Hook, body và close

TikTok mô tả cấu trúc sáng tạo gồm ba phần: hook để giành chú ý, body để củng cố sản phẩm/brand, và close với CTA mạnh. Value proposition nên xuất hiện sớm trong sáu giây đầu; brand cue trong hook nên tự nhiên và không làm suy yếu chính hook. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf))

TikTok gợi ý các họ hook như vấn đề/pain point, tips/hacks, review/popularity và unboxing; phần giữa phải nối thông điệp chính với selling point một cách mạch lạc; phần cuối dùng text, voice-over hoặc graphics để thúc đẩy hành động. Đây là thư viện pattern, không phải lý do để tạo claim không kiểm chứng. ([Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en), [Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content))

TikTok khuyên nội dung "TikTok First": dọc, độ phân giải cao, có người thật/creator-style, dựng nhanh, text overlay kiểu native và cảm giác chân thực thay vì bóng bẩy như TVC. Checklist chính thức yêu cầu 9:16, tối thiểu 720p, sản phẩm vật lý đủ sáng và nhìn rõ chi tiết. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf), [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf))

### Nhịp dựng, âm thanh và CTA

TikTok liệt kê music, transitions, movement, text và scene changes như attention triggers; đồng thời khuyên sound-on, voice-over rõ và ngắn, sound effect đồng bộ với hành động, và nhạc từ Commercial Music Library đã được clearance cho mục đích thương mại. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf), [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en))

CTA phải phù hợp mục tiêu quảng cáo và nhất quán với sản phẩm/landing page. Các CTA hoặc gesture mô phỏng chức năng không tồn tại, ví dụ nút giả hoặc lời "swipe up" không dẫn đến hành động tương ứng, có thể vi phạm chất lượng/quy định quảng cáo. ([Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf), [Ad format and functionality](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en))

### Safe zone và thông số hiển thị

TikTok khuyến nghị video dọc 9:16; thông số Non-Spark In-Feed hiện tại yêu cầu ít nhất 540x960 cho bản dọc, còn checklist chất lượng khuyên từ 720p trở lên. Nội dung quan trọng, sản phẩm, logo và text phải nằm trong safe zone. ([In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB), [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf))

Safe zone co lại khi caption dài hơn hoặc khi dùng anchor/add-on, và preview có thể khác nhẹ theo thiết bị. Vì vậy không nên hard-code một hình chữ nhật duy nhất vào prompt; cần lưu `placement`, `caption_lines`, `anchor_type`, `safe_zone_asset_version` và kiểm tra bằng Preview Tool trước khi phát hành. Đây là **suy luận triển khai** dựa trên thông số chính thức. ([In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB), [Download Card safe zone](https://ads.tiktok.com/help/article/tiktok-interactive-add-on-download-card-ad-specifications?lang=en))

## 2. Disclosure và compliance cho affiliate/AIGC

TikTok định nghĩa tín hiệu commercial content gồm lợi ích tài chính, brand mention và product recommendation/CTA. Nội dung affiliate vì có hoa hồng hoặc lợi ích khác phải bật disclosure; nội dung cho bên thứ ba được gắn nhãn "Paid partnership", còn quảng bá doanh nghiệp của chính mình được gắn "Promotional content". ([Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en), [Promoting a brand/product/service](https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/promoting-a-brand-product-or-service))

TikTok nói bật disclosure không làm giảm phân phối theo cơ chế đề xuất, nhưng không disclosure đúng có thể khiến video mất điều kiện xuất hiện ở For You hoặc bị hạn chế/xóa. Pipeline nên xuất `commercial_disclosure_required: true` và một pre-publish checklist thay vì chỉ chèn chữ quảng cáo vào nội dung hình. ([Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en), [Promoting a brand/product/service](https://support.tiktok.com/en/business-and-creator/creator-and-business-accounts/promoting-a-brand-product-or-service))

TikTok cho phép AIGC/chỉnh sửa đáng kể nếu có AIGC label hoặc disclaimer/caption/watermark/sticker rõ ràng; quảng cáo AIGC không disclosure có thể bị từ chối hoặc hạn chế. TikTok cũng cấm dùng likeness người nổi tiếng cho endorsement giả và có thể gỡ likeness người riêng tư dùng không có phép. ([Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content), [TikTok AIGC support](https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content))

Nội dung và landing page không được phóng đại hiệu quả, dùng claim tuyệt đối, before/after gây hiểu sai, hoặc bất nhất về sản phẩm, brand, giá và discount. CTA, caption, hình, video và landing page phải mô tả cùng một offer. ([Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content), [Ad format and functionality](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en))

## 3. Tài liệu model và hệ quả cho prompt

### Ảnh nền/keyframe

Imagen khuyên prompt ảnh bắt đầu từ `subject + context/background + style`, sau đó bổ sung camera proximity/position, lighting, camera settings và lens khi cần. Imagen cũng hỗ trợ 9:16 và khuyên text sinh trực tiếp trong ảnh ngắn không quá 25 ký tự; vì text trong ảnh vẫn có sai lệch, **suy luận triển khai** là CTA/subtitle quan trọng nên được render ở hậu kỳ thay vì phụ thuộc hoàn toàn vào image model. ([Imagen prompt guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/img-gen-prompt-guide))

Reference asset nên có vai trò tách biệt: reference nhân vật/sản phẩm cho identity, composition reference cho bố cục, style reference cho màu/texture/ánh sáng. Firefly xác nhận composition reference điều khiển outline/depth và style reference giúp duy trì look nhất quán giữa nhiều asset. ([Firefly composition reference](https://helpx.adobe.com/firefly/web/work-with-images/generate-images/match-image-composition-to-reference-image.html), [Firefly style reference](https://helpx.adobe.com/uk/firefly/how-to/generate-image-using-reference-image.html))

Khi dùng nhiều keyframe, Runway khuyên các ảnh chia sẻ cùng chủ thể, cảnh và style để chuyển động tự nhiên; khác biệt quá lớn tạo kết quả bất ngờ, và chuyển đổi phức tạp cần thời lượng dài hơn. **Suy luận triển khai:** keyframe validator nên đo/kiểm tra identity, background, palette, product geometry và độ chênh pose trước khi gửi model. ([Runway Keyframes](https://help.runwayml.com/hc/en-us/articles/34170748696595-Creating-with-Keyframes-on-Gen-3))

### Image-to-video và camera motion

Runway và Veo đều hướng dẫn coi ảnh input là first frame đã chứa subject/composition/lighting/style, còn text prompt chủ yếu mô tả motion. Cấu trúc khởi đầu phù hợp là `The camera [movement] as the subject [action]. [environment/timing]`; dùng ngôn ngữ trực tiếp, hành động vật lý cụ thể và tên gọi chung như "the subject" thay vì lặp lại toàn bộ appearance. ([Runway Image-to-Video Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide), [Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice))

Runway khuyên prompt đơn giản, positive phrasing và bổ sung từng thành phần khi iterate; một clip ngắn nên là một scene thay vì chuỗi biến đổi theo từng giây. **Suy luận triển khai:** `motion_prompt` nên có một `primary_camera_move`, một `primary_subject_action`, tối đa một `environmental_motion`, cùng `speed` và `end_state`; beat sheet chi tiết dùng cho editor, không đổ nguyên văn vào model. ([Runway Gen-4 Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide))

Veo và Luma hỗ trợ first/last frames; Luma còn nhận camera motion bằng cụm từ ngôn ngữ. Đây là bằng chứng để adapter hóa capability thay vì giả định mọi model hiểu sáu timestamp text keyframes. ([Veo first/last frames](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-first-and-last-frames), [Luma video API](https://docs.lumalabs.ai/ue/docs/video-generation))

## 4. Schema trung gian đề xuất

Schema dưới đây là **suy luận triển khai** từ hướng dẫn TikTok về structure/safe zone/compliance và hướng dẫn model về reference/keyframe/motion. ([Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf), [In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB), [Runway Image-to-Video Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide), [Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice))

```ts
type AffiliateVideoPlan = {
  objective: "click" | "product_view" | "add_to_cart" | "purchase";
  audience: { market: string; persona: string; pain_point: string };
  offer: {
    product_id: string;
    product_name: string;
    verified_features: string[];
    verified_price?: string;
    verified_discount?: string;
    landing_page_url: string;
  };
  creative: {
    single_value_proposition: string;
    hook: {
      type: "pain_point" | "demo_result" | "review" | "unboxing" | "tip";
      visible_by_s: number;       // internal target: <= 2
      payoff_by_s: number;        // official evidence boundary: <= 6
    };
    proof_or_demo: string;
    cta: { action: string; destination: string };
    total_duration_s: number;
    scenes: ScenePlan[];
  };
  format: {
    aspect_ratio: "9:16";
    min_resolution: "720x1280";
    placement: "organic" | "spark" | "non_spark";
    caption_lines: number;
    anchor_type?: string;
    safe_zone_asset_version: string;
  };
  compliance: {
    commercial_disclosure_required: boolean;
    aigc_disclosure_required: boolean;
    music_rights: "commercial_music_library" | "owned" | "licensed";
    claims_evidence_ids: string[];
    prohibited_claims_found: string[];
    offer_matches_landing_page: boolean;
  };
  generation: {
    image_model: string;
    video_model: string;
    seed?: number;
    identity_reference_ids: string[];
    product_reference_ids: string[];
    composition_reference_id?: string;
    style_reference_id?: string;
    provider_capabilities: {
      first_frame: boolean;
      middle_frame: boolean;
      last_frame: boolean;
      camera_control: boolean;
      supported_durations_s: number[];
    };
  };
};

type ScenePlan = {
  purpose: "hook" | "body" | "proof" | "close";
  duration_s: number;
  continuity_in: string;
  continuity_out: string;
  product_state: {
    location: string;
    orientation: string;
    visibility: "hero" | "clear" | "background";
    interaction: string;
  };
  image_prompt: {
    subject: string;
    context: string;
    style: string;
    composition: string;
    camera_angle: string;
    lens: string;
    lighting: string;
    safe_zone_instruction: string;
  };
  story_beats: Array<{ at_s: number; action: string; product_state: string }>;
  provider_keyframes: {
    first?: string;
    middle?: string;
    last?: string;
  };
  motion_prompt: {
    primary_camera_move: string;
    primary_subject_action: string;
    environmental_motion?: string;
    speed: "slow" | "moderate" | "fast";
    end_state: string;
    continuous_shot: boolean;
  };
};
```

## 5. Prompt constraints có thể tự động kiểm tra

| Tầng | Constraint đề xuất | Căn cứ |
|---|---|---|
| Concept | Một audience pain point, một value proposition, một proof/demo, một CTA; hook xuất hiện <=2 giây và payoff <=6 giây. | **Suy luận triển khai** từ [Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf) và [Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en). |
| Breakdown | Số cảnh và duration lấy từ objective/provider; mỗi cảnh có đúng một narrative purpose và một product state; tổng duration phải bằng tổng scene duration. | **Suy luận triển khai** từ [Runway Gen-4 Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide) và [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf). |
| Image prompt | Bắt buộc subject, context, style, composition, camera, lighting, product location/visibility và safe-zone instruction; dùng identity/product reference riêng. | **Suy luận triển khai** từ [Imagen prompt guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/img-gen-prompt-guide) và [Firefly references](https://helpx.adobe.com/firefly/web/work-with-images/generate-images/match-image-composition-to-reference-image.html). |
| Keyframe | `story_beats` không đồng nghĩa `provider_keyframes`; chỉ tạo first/middle/last theo capability; keyframes phải giữ cùng identity, product geometry, scene và style. | **Suy luận triển khai** từ [Runway Keyframes](https://help.runwayml.com/hc/en-us/articles/34170748696595-Creating-with-Keyframes-on-Gen-3), [Veo first/last frames](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-first-and-last-frames) và [Luma API](https://docs.lumalabs.ai/ue/docs/video-generation). |
| Motion prompt | Một camera move chính, một subject action chính, tối đa một environmental motion; mô tả hướng/tốc độ/end-state; không lặp appearance đã có trong first frame. | **Suy luận triển khai** từ [Runway Image-to-Video Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide) và [Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice). |
| Audio | Voice-over phải rõ; nhạc thương mại chỉ từ CML/owned/licensed; audio cue phải gắn với hook/action. | [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf) và [Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf). |
| Compliance | Bắt buộc commercial disclosure cho affiliate; AIGC disclosure cho nội dung AI đáng kể; mọi claim phải có evidence; offer/CTA phải khớp landing page. | [Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en), [AIGC policy](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content) và [Ad consistency](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en). |
| Render QA | 9:16, >=720x1280, product/text/logo trong safe-zone mask đúng placement, subtitle đọc được, không có fake UI/CTA. | [Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf), [In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB) và [Ad format policy](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en). |

## 6. Cổng QA trước khi phát hành

1. `claim_gate`: đối chiếu từng câu benefit, price, discount và superlative với product source/landing page; fail nếu thiếu evidence hoặc dùng kết quả tuyệt đối/phóng đại. ([Misleading and false content](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content))
2. `disclosure_gate`: fail nếu affiliate nhưng `commercial_disclosure_required=false`, hoặc AIGC đáng kể nhưng không có AIGC label/disclaimer. ([Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en), [AIGC policy](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content))
3. `continuity_gate`: so first/middle/last frame về identity, product shape/logo/color, wardrobe, background và light direction; regenerate trước khi animate nếu chênh quá ngưỡng. Đây là **suy luận triển khai** từ yêu cầu keyframe tương đồng và reference consistency. ([Runway Keyframes](https://help.runwayml.com/hc/en-us/articles/34170748696595-Creating-with-Keyframes-on-Gen-3), [Firefly style reference](https://helpx.adobe.com/uk/firefly/how-to/generate-image-using-reference-image.html))
4. `motion_gate`: fail nếu một clip chứa nhiều scene change, nhiều camera move cạnh tranh hoặc action mâu thuẫn với pose/motion cue của ảnh đầu. ([Runway Gen-4 Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide), [Runway Image-to-Video Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide))
5. `layout_gate`: render overlay safe-zone theo placement/caption/anchor, kiểm tra từng frame có CTA, subtitle, product hoặc logo quan trọng; sau đó xác nhận lại bằng TikTok Preview Tool. ([In-Feed specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB), [Download Card safe zone](https://ads.tiktok.com/help/article/tiktok-interactive-add-on-download-card-ad-specifications?lang=en))
6. `audio_gate`: kiểm tra voice-over nghe rõ trên nền nhạc, quyền sử dụng nhạc và audio hook đồng bộ với hình. ([Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf), [Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf))

## Nguồn chính

- [TikTok Creative Codes](https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf)
- [TikTok Creative Accelerator](https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en)
- [TikTok Creative Quality Checklist](https://ads.tiktok.com/business/library/7TopCreativeTips.pdf)
- [TikTok Auction In-Feed Ads specifications](https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en-GB)
- [TikTok Commercial Content Disclosure](https://ads.tiktok.com/help/article/about-the-commercial-content-disclosure-setting-for-advertisers?lang=en)
- [TikTok Misleading and false content/AIGC](https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content)
- [TikTok Ad format and functionality](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en)
- [Google Imagen prompt guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/img-gen-prompt-guide)
- [Google Veo best practices](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice)
- [Google Veo first/last frame generation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-first-and-last-frames)
- [Runway Image-to-Video Prompting Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide)
- [Runway Gen-4 Video Prompting Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide)
- [Runway Keyframes Guide](https://help.runwayml.com/hc/en-us/articles/34170748696595-Creating-with-Keyframes-on-Gen-3)
- [Luma AI Video Generation API](https://docs.lumalabs.ai/ue/docs/video-generation)
- [Adobe Firefly composition reference](https://helpx.adobe.com/firefly/web/work-with-images/generate-images/match-image-composition-to-reference-image.html)
- [Adobe Firefly style reference](https://helpx.adobe.com/uk/firefly/how-to/generate-image-using-reference-image.html)
