from pathlib import Path


def test_product_research_is_not_semantically_routed_by_telegram_channel():
    from hermes.channels.gateway.platforms.telegram import bot

    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "is_product_research_script_request" not in source
    assert "run_orchestrator_turn(update, user_text)" in source
