"""Regression tests for server startup worker wiring."""

import ast
from pathlib import Path


def _main_called_function_names() -> set[str]:
    source = Path(__file__).resolve().parents[1] / "openrecall" / "server" / "__main__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    main_def = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    called: set[str] = set()
    for node in ast.walk(main_def):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    return called


def _preload_called_function_names() -> set[str]:
    source = Path(__file__).resolve().parents[1] / "openrecall" / "server" / "__main__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    preload_def = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "preload_ai_models"
    )
    called: set[str] = set()
    for node in ast.walk(preload_def):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    return called


def test_server_main_starts_background_worker():
    called = _main_called_function_names()
    assert "init_background_worker" in called


def test_server_main_starts_video_worker():
    called = _main_called_function_names()
    assert "init_video_worker" in called


def test_server_preload_ai_models_includes_ocr_warmup():
    called = _preload_called_function_names()
    assert "get_ocr_provider" in called
