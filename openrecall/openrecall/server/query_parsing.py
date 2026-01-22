from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


_WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


@dataclass(frozen=True)
class ParsedQuery:
    q_semantic: str
    q_keywords: str
    start_ts: int | None
    end_ts: int | None


def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _day_end(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)


def _week_start(dt: datetime) -> datetime:
    d = _day_start(dt)
    return d - timedelta(days=d.weekday())


def _strip_tokens(q: str, tokens: list[str]) -> str:
    out = q
    for t in tokens:
        if not t:
            continue
        out = out.replace(t, " ")
    return re.sub(r"\s+", " ", out).strip()


def parse_time_range(q: str, now: datetime | None = None) -> tuple[int | None, int | None, str]:
    text = (q or "").strip()
    if not text:
        return None, None, ""
    now_dt = now or datetime.now()

    matched: list[str] = []

    def set_range(start: datetime, end: datetime):
        return int(start.timestamp()), int(end.timestamp())

    day_offset = 0
    if "前天" in text:
        matched.append("前天")
        day_offset = -2
    elif "昨天" in text:
        matched.append("昨天")
        day_offset = -1
    elif "今天" in text:
        matched.append("今天")
        day_offset = 0

    part = None
    for token in ["凌晨", "上午", "中午", "下午", "晚上"]:
        if token in text:
            matched.append(token)
            part = token
            break

    start_ts = None
    end_ts = None

    if day_offset is not None and any(t in matched for t in ["前天", "昨天", "今天"]):
        base = _day_start(now_dt + timedelta(days=day_offset))
        if part == "凌晨":
            start_ts, end_ts = set_range(base, base.replace(hour=5, minute=59, second=59))
        elif part == "上午":
            start_ts, end_ts = set_range(base.replace(hour=6), base.replace(hour=11, minute=59, second=59))
        elif part == "中午":
            start_ts, end_ts = set_range(base.replace(hour=12), base.replace(hour=13, minute=59, second=59))
        elif part == "下午":
            start_ts, end_ts = set_range(base.replace(hour=12), base.replace(hour=17, minute=59, second=59))
        elif part == "晚上":
            start_ts, end_ts = set_range(base.replace(hour=18), _day_end(base))
        else:
            start_ts, end_ts = set_range(base, _day_end(base))

    m = re.search(r"最近\s*(\d+)\s*天", text)
    if m:
        matched.append(m.group(0))
        days = int(m.group(1))
        start = _day_start(now_dt - timedelta(days=max(days, 1) - 1))
        start_ts, end_ts = set_range(start, _day_end(now_dt))

    m = re.search(r"(\d+)\s*天前", text)
    if m:
        matched.append(m.group(0))
        days = int(m.group(1))
        base = _day_start(now_dt - timedelta(days=days))
        start_ts, end_ts = set_range(base, _day_end(base))

    m = re.search(r"上周([一二三四五六日天])", text)
    if m:
        matched.append(m.group(0))
        weekday = _WEEKDAY_MAP[m.group(1)]
        start_of_this_week = _week_start(now_dt)
        target_day = start_of_this_week - timedelta(days=7 - weekday)
        start_ts, end_ts = set_range(_day_start(target_day), _day_end(target_day))

    m = re.search(r"本周([一二三四五六日天])", text)
    if m:
        matched.append(m.group(0))
        weekday = _WEEKDAY_MAP[m.group(1)]
        target_day = _week_start(now_dt) + timedelta(days=weekday)
        start_ts, end_ts = set_range(_day_start(target_day), _day_end(target_day))

    if "上周" in text and not any(t.startswith("上周") and len(t) > 2 for t in matched):
        matched.append("上周")
        start_of_this_week = _week_start(now_dt)
        start_ts, end_ts = set_range(start_of_this_week - timedelta(days=7), start_of_this_week - timedelta(seconds=1))

    if "本周" in text and not any(t.startswith("本周") and len(t) > 2 for t in matched):
        matched.append("本周")
        start_ts, end_ts = set_range(_week_start(now_dt), _day_end(now_dt))

    cleaned = _strip_tokens(text, matched) if matched else text
    return start_ts, end_ts, cleaned


def split_query(q: str, now: datetime | None = None) -> ParsedQuery:
    start_ts, end_ts, cleaned = parse_time_range(q, now=now)
    cleaned = (cleaned or "").strip()
    return ParsedQuery(
        q_semantic=cleaned,
        q_keywords=cleaned,
        start_ts=start_ts,
        end_ts=end_ts,
    )
