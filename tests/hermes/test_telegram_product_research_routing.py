from __future__ import annotations


def test_product_research_detector_matches_sheet_and_script_request():
    import telegram_bot

    assert telegram_bot.is_product_research_script_request(
        "crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản"
    )
    assert not telegram_bot.is_product_research_script_request("hôm nay thời tiết sao")