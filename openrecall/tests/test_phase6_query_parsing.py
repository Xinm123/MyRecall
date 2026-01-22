from datetime import datetime

import pytest


@pytest.mark.parametrize(
    "q,expect_clean",
    [
        ("昨天 修bug", "修bug"),
        ("昨天下午 修改代码BUG", "修改代码BUG"),
        ("今天上午 写文档", "写文档"),
        ("前天晚上 看日志", "看日志"),
        ("今天中午 吃饭", "吃饭"),
        ("昨天凌晨 排查", "排查"),
        ("最近3天 打开IDE", "打开IDE"),
        ("最近 1 天 编译", "编译"),
        ("3天前 修复", "修复"),
        ("10天前 发布", "发布"),
        ("上周三 代码", "代码"),
        ("上周一 测试", "测试"),
        ("上周 会议", "会议"),
        ("本周 计划", "计划"),
        ("本周四 任务", "任务"),
        ("昨天", ""),
        ("今天", ""),
        ("前天", ""),
        ("上周三", ""),
        ("上周", ""),
        ("本周", ""),
    ],
)
def test_parse_time_range_cleans_query(q, expect_clean):
    from openrecall.server.query_parsing import parse_time_range

    now = datetime(2026, 1, 22, 15, 30, 0)
    _start, _end, cleaned = parse_time_range(q, now=now)
    assert cleaned == expect_clean


def test_yesterday_afternoon_window():
    from openrecall.server.query_parsing import parse_time_range

    now = datetime(2026, 1, 22, 15, 30, 0)
    start_ts, end_ts, cleaned = parse_time_range("昨天下午 修改代码BUG", now=now)
    assert cleaned == "修改代码BUG"
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)
    assert start.date().isoformat() == "2026-01-21"
    assert start.hour == 12
    assert end.hour == 17


def test_last_week_wednesday():
    from openrecall.server.query_parsing import parse_time_range

    now = datetime(2026, 1, 22, 15, 30, 0)
    start_ts, end_ts, cleaned = parse_time_range("上周三 代码", now=now)
    assert cleaned == "代码"
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)
    assert start.date().isoformat() == "2026-01-14"
    assert start.hour == 0
    assert end.hour == 23


def test_recent_days_range():
    from openrecall.server.query_parsing import parse_time_range

    now = datetime(2026, 1, 22, 15, 30, 0)
    start_ts, end_ts, cleaned = parse_time_range("最近3天 打开IDE", now=now)
    assert cleaned == "打开IDE"
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)
    assert start.date().isoformat() == "2026-01-20"
    assert end.date().isoformat() == "2026-01-22"
