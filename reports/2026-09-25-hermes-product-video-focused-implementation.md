# Hermes Product Video — danh sách triển khai tập trung

**Ngày:** 2026-09-25  
**Phạm vi:** các điểm nghẽn trong báo cáo rà soát toàn dự án, ưu tiên tạo và kiểm soát video cá nhân. Đây là thay đổi trên working tree hiện có; không chạy test E2E theo yêu cầu. Phần vận hành tiếp theo có chạy Image QC thật với hạn mức chi phí riêng cho từng workflow.

## Đã triển khai trong lượt này

1. **Video QC mâu thuẫn về viền đen:** nếu evaluator kết luận FAIL vì black bars nhưng detector kỹ thuật đã lấy mẫu và không thấy viền đen, kết quả chuyển sang `UNKNOWN` và yêu cầu kiểm tra thủ công. Không tự động PASS trên kết quả mâu thuẫn. Mã: `hermes_personal/product_video/qc/video_qc.py`.
2. **Render Google Flow có kết quả chưa rõ:** lớp MCP giữ nguyên `RECONCILIATION_REQUIRED`; handler dừng retry trả phí, giữ budget reservation để đối soát. Nếu đã checkpoint job ID thì retry chỉ poll job đó, dùng lại và commit reservation ban đầu. Nếu mất phản hồi trước checkpoint thì trả `UNKNOWN_PAID_OUTCOME`, không tự nộp lại. Mã: `hermes_personal/product_video/mcp_adapters.py`, `hermes_personal/product_video/handlers.py`.
3. **Provenance của export mới:** approval được lấy từ workflow/project/owner và đúng gate; final approval phải khớp artifact/version. Manifest lấy operation, SHA, QC report ID từ bản ghi đã xác thực. Không chép ID, digest hoặc chi phí do caller tự khai; khi chưa có actual cost, ghi `unavailable`. Mã: `hermes_personal/integrations/video_factory/server.py`.
4. **Tài liệu vận hành:** sửa mô tả sai về worker/MCP/Telegram runner, middleware và static digest; ghi rõ cách xử lý Flow reconciliation và giới hạn credit hiện tại. Master Idea ghi trạng thái thực tế của Flow, Vertex, audio và mục tiêu 3–5 video/ngày. Tài liệu: `docs/infrastructure.md`, `docs/hermes-personal/product-video-runbook.md`, `reports/hermes-master-idea.html`.

## Kiểm tra cơ bản

- `uv run pytest tests/hermes_personal/product_video/test_video_qc.py tests/hermes_personal/product_video/test_export_integrity.py tests/hermes_personal/product_video/test_review_rework.py -q --tb=short`: **81 passed**.
- `uv run ruff check` cho các file Python đã sửa và ba file test trên: **pass**.
- Không chạy E2E, toàn bộ suite, Flow/Vertex trả phí hoặc xuất lại MP4.

## Còn lại trước khi gọi là sản xuất tự động hoàn chỉnh

1. **Flow live:** workflow đang mắc ở `rendering` phải được đối soát với đúng Flow project/tile và chạy qua export. Thay đổi trên ngăn retry mù; chưa chứng minh Flow đã tạo được clip trong lượt này.
2. **Credit Flow:** hiện adapter đọc giá credit hiển thị nhưng chưa kiểm tra số dư thực, chưa có ledger 50/ngày + 1.000/tháng và chưa chọn model theo từng cảnh. Không thể bảo đảm 3–5 video hoàn chỉnh/ngày hoặc tự chuyển Vertex theo số dư. Provider phải được chọn trước khi tạo cảnh trả phí, trong budget Vertex đã duyệt.
3. **Audio:** MP4 Vertex hiện có không chứa lời dẫn đã duyệt. Cần một bước tạo và duyệt voice asset, ghép theo cảnh, QC audio và xuất version mới; file hiện tại chỉ là bản hình.
4. **Actual cost:** ngân sách hiện là mức đặt chỗ/giới hạn; chưa đối soát hóa đơn thực từ provider. Manifest mới khai báo `unavailable` thay vì một số giả định.
5. **QC/rework:** nhánh `UNKNOWN` chặn tự duyệt nhưng chưa tạo clip thay thế tự động. Operator tiếp tục xử lý theo năm gate hiện có.

**Trạng thái:** nhánh Vertex đã có một video hình thật theo báo cáo rà soát. Nhánh Flow và video có lời dẫn chưa được nghiệm thu; chưa nên tuyên bố hệ thống tự sản xuất 3–5 video hoàn chỉnh mỗi ngày.

## Tiếp tục triển khai: mục tiêu 3–5 video/ngày theo best effort

1. Coordinator nhận tối đa 5 sản phẩm PI từ batch `READY` theo thứ tự ưu tiên. Một lần chạy lại trong cùng ngày chỉ lấp số slot còn thiếu, không tạo workflow trùng. CLI, REST và Operator Console dùng cùng giới hạn 5.
2. CLI `start --auto --limit 5 --minimum-daily 3 --date today` trả lỗi nếu ngày đó bắt đầu dưới 3 workflow; REST trả `INSUFFICIENT_DAILY_PRODUCTS` cùng số lượng thực. Lệnh `daily-status` đếm workflow đã hoàn thành thành MP4, in từng trạng thái và trả lỗi nếu dưới 3.
3. `ExchangeImporter.validate_admission` loại tên dạng URL/marketplace slug, tên không xác định brand hoặc model có dạng giá. Đây là kiểm tra đầu vào; Product Lock tiếp tục quyết định danh tính và nguồn ảnh.
4. Windows Task Scheduler đã đăng ký `HermesProductVideoDaily` lúc **07:15** và `HermesProductVideoDailyReport` lúc **20:00** hằng ngày. Cả hai gọi `scripts/run_product_video_daily.ps1`, ghi `D:/work/hermes-agent-data/logs/product-video-daily.log` và trả exit code lỗi khi thiếu sản phẩm/video. Không có tác vụ nào tự duyệt năm gate.

**Bằng chứng ngày 2026-09-25:** Product Intelligence đã xuất batch `READY` với 3 mục nhưng cả 3 bị loại vì tên URL/tên chủ đề không khớp brand hoặc model dạng giá; intake thực tế báo `0/3` và exit code 1, không gọi provider trả phí. Completion check cũng báo `0/3` và exit code 1. Đây là lỗi dữ liệu nguồn hiển thị đúng, không phải chạy thất bại im lặng.

**Kiểm tra cơ bản cho phần tiếp tục:** 21 test CLI/coordinator/route qua; Ruff qua; PowerShell 5.1 parse qua. Không chạy E2E hay render trả phí.

## Sửa tiếp dữ liệu nguồn Product Intelligence

Ở repo `D:/work/Personal/Product-Intelligence`, bộ nhận diện nay chuyển tiêu đề marketplace dạng slug thành tên dễ đọc, chỉ lấy model từ tiêu đề sản phẩm (không lấy giá hoặc model lạc trong nhận xét), và bộ chọn loại ứng viên thiếu brand/model đáng tin cậy trước khi xuất batch. Batch `READY` ngày 2026-09-25 được giữ nguyên để bảo toàn lịch sử; thay đổi áp dụng cho các lần quét mới.

Kiểm tra ngắn tại repo nguồn: **25 test qua**, Ruff qua, `git diff --check` qua. Lần quét mạng sau đó không tìm được sản phẩm hợp lệ; xem kết quả vận hành bên dưới.

## Chính sách lời dẫn tùy chọn

Scene Plan đã duyệt tiếp tục là nguồn lời dẫn. Video prompt gửi lời dẫn tiếng Việt cho Google Flow; Vertex Veo 3 nhận thêm `generateAudio=true` khi cảnh có lời dẫn. Clip không có audio vẫn có thể qua QC và xuất MP4 không lời. Nếu chỉ một số clip có audio, composer bỏ audio ở bản ghép để tránh thoại bị lệch cảnh. Không tự nộp lại một operation trả phí chỉ vì clip im lặng; trạng thái `has_audio` lấy từ probe của file thật.

Kiểm tra ngắn: **37 test qua**, Ruff qua. Chưa gọi Flow/Vertex thật; MP4 cũ vẫn không lời, chất lượng giọng AI chưa được xác nhận.

## Vận hành thật và sửa lỗi hiển thị ngày 2026-09-25

- Product Intelligence được chạy lại trên mạng. Nguồn tìm kiếm không cho ra ứng viên đủ nhận diện; runner nay báo `no_eligible_products` và không ghi đè một lần chạy thành công bằng danh sách rỗng. Bộ lọc đầu vào loại ứng viên mơ hồ trước khi chiếm hạn mức làm giàu 30 mục. Các thay đổi ở repo `D:/work/Personal/Product-Intelligence`.
- Dùng batch PI `READY` lịch sử **2026-09-18** để kiểm tra đường chạy thật, không tính là đầu vào mới của ngày 2026-09-25. Đã bắt đầu 5 workflow đúng trần ngày: Jisulife, Baseus WM02, QCY T13 ANC, Tribit XSound Go, Imou Ranger 2. Không có workflow nào hoàn thành MP4 (`0/3`).
- Jisulife có hai canonical product (`Fan 7` và `Life 7`), nên resource pack không thể khóa. Adapter nay báo `NON_LOCKABLE_STATUS` cùng lý do mơ hồ trước khi kiểm tra số ảnh; bản ghi lỗi cũ trong SQLite vẫn giữ thông điệp `media_count 0` của mã cũ. QCY và Imou không có canonical evidence, đã bị cách ly; không tự thử lại vô hạn.
- Baseus WM02 có resource pack nhưng Image QC thật trả **FAIL**, 31 điểm, 0 ảnh đủ điều kiện. Nguồn có banner quảng cáo và màu sản phẩm không khớp biến thể mà nghiên cứu nhận diện. Không tạo Product Lock.
- Tribit XSound Go có resource pack 4 ảnh; Image QC thật trả **PASS**, 100 điểm, **2 ảnh đủ điều kiện**. Workflow `pv-daily-fbbc4a42ce5fe778` đang ở `AwaitingProductLock`; approval ID `df96ca9b-09ca-4768-b396-551ac9330bb2`. Nguồn claim IPX7 là trang sản phẩm `https://tribit.com/products/Tribit-XSound-Go-Bluetooth-Speakers`; hai ảnh đủ điều kiện là ảnh loa thật với logo Tribit. Chưa tự duyệt Product Lock hoặc các gate sau.
- `status` và `daily-status` nay hiển thị lỗi outbox `quarantined` khi aggregate còn ở bước research/resource pack, thay vì chỉ ghi “đang sản xuất”. Image QC FAIL cũng hiện hướng xử lý ảnh trước Product Lock. PI resource pack loại claim trùng lặp từ cùng một evidence trong các lần dựng mới.

**Kiểm tra tập trung:** test hợp đồng adapter, hiển thị quarantine và khử claim trùng lặp đều qua; Ruff qua. Không chạy suite E2E hay render Flow/Vertex trả phí. QC Image là hai lần gọi thật có authorization riêng, mỗi lần giới hạn USD 0,10; giới hạn đặt chỗ không phải chi phí thực tế đã đối soát.

## Chạy workflow Hermes sau khi duyệt Product Lock

- Dùng Hermes upstream CLI và durable worker để tiếp tục workflow Tribit `pv-daily-fbbc4a42ce5fe778`. Hermes đã tạo Creative Brief, Scene Plan, Storyboard và bắt đầu sinh keyframe. Codex chỉ kiểm tra các cổng và sửa điểm nghẽn cụ thể; chưa có MP4 mới.
- Dossier từ PI bỏ sót claim dù trang `tribit.com` là nguồn hãng. Sửa nhận diện URL hãng, khử claim trùng và dựng lại dossier từ resource pack đã khóa khi outbox còn payload cũ. Brief sau đó được Hermes tạo và duyệt bằng approval `d07b8ad7-a317-4f66-860e-1e0de5784dcd`.
- Scene Plan đầu chứa cảnh loa nổi/tiếp tục phát dưới nước không được bằng chứng IPX7 hỗ trợ. Hermes sinh lại bốn cảnh với phản hồi operator; bản an toàn được lưu phiên bản 2. Prompt mặc định bỏ ví dụ rung nước do bass và cấm suy diễn IPX7 thành các bảo đảm không có bằng chứng.
- Model trả `schema_version=ScriptScenePlanV2`, khiến bản Scene Plan sửa lần đầu không đọc lại được và worker rơi sang Storyboard cũ không có keyframe. Bộ sinh nay chuẩn hóa thành `script-scene-plan-v2`. Bản đã lưu được sửa thành phiên bản 3 qua cơ chế revision/approval của Hermes, không ghi đè bản trước.
- Sau khi duyệt Scene Plan v3 bằng approval `1f9da881-f6e9-4262-b4ff-a4df5d00254c`, worker đã tạo **6 keyframe thật** bằng Vertex. Frame `scene_4_cta_payoff-start` timeout sau 120 giây với `NETWORK_UNKNOWN_OUTCOME`; outbox 67 bị `quarantined`. API tạo ảnh đồng bộ không cung cấp job ID truy vấn; đối soát local trả `RECONCILIATION_REQUIRED`. Không gửi lại operation trả phí khi chưa rõ kết quả.
- **Trạng thái hiện tại:** `creating_storyboard`, chưa có Keyframe QC PASS, chưa tới Gate Storyboard, chưa render video, chưa xuất MP4. Batch PI ngày 2026-09-25 vẫn không có sản phẩm mới đủ điều kiện; các workflow đang thử dùng batch lịch sử 2026-09-18.

**Kiểm tra cơ bản:** `test_creative_generator.py` 3 passed; Ruff trên hai file creative qua; kiểm tra tại runtime xác nhận phản hồi model có schema sai được chuẩn hóa, feedback vào prompt và kịch bản đọc lại/validate được. Không chạy E2E.
