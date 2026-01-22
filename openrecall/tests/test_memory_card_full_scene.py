from openrecall.server.memory_card import build_memory_card, extract_human_description


def test_extract_human_description_from_vision_json():
    raw = '{"app":"VSCode","scene":"在 VSCode 中调试 Python 程序","actions":["调试","修复错误"],"entities":["TypeError"],"description":"在 VSCode 中调试并修复 TypeError 错误。"}'
    assert extract_human_description(raw) == "在 VSCode 中调试并修复 TypeError 错误。"


def test_memory_card_truncates_code_and_keeps_scene():
    ocr = "\n".join(
        ["def foo(x):", "    return x + 1"]
        + [f"    v{i} = foo({i})" for i in range(300)]
        + ["", "Settings", "Search", "Meeting notes", "Traceback (most recent call last):", "TypeError: boom"]
    )
    vision = '{"app":"VSCode","scene":"在 VSCode 中调试 Python 程序","actions":["调试","修复错误"],"entities":["TypeError"],"description":"在 VSCode 中调试并修复 TypeError 错误。"}'
    card = build_memory_card(
        app="VSCode",
        title="main.py — VSCode",
        timestamp=1710000000,
        ocr_text=ocr,
        vision_description=vision,
        code_max_lines=30,
        traceback_max_lines=10,
        max_chars=900,
    )
    assert "[SCENE]" in card.embedding_text
    assert "在 VSCode 中调试并修复 TypeError 错误" in card.embedding_text
    assert "[CODE]" in card.embedding_text
    assert len(card.code) <= 30
    assert "[TRACEBACK]" in card.embedding_text
    assert any("Traceback" in ln for ln in card.traceback)
    assert len(card.embedding_text) <= 900
