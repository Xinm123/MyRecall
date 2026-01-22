import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime


def _extract_first_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_vision_meta(text: str | None) -> dict | None:
    return _extract_first_json_object((text or "").strip())


def extract_human_description(text: str | None) -> str:
    raw = (text or "").strip()
    meta = parse_vision_meta(raw)
    if isinstance(meta, dict):
        v = meta.get("description")
        if isinstance(v, str) and v.strip():
            return v.strip()
        v = meta.get("scene")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return raw


def _time_bucket(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts))
    except Exception:
        return ""
    h = dt.hour
    if 5 <= h < 11:
        return "早上"
    if 11 <= h < 13:
        return "中午"
    if 13 <= h < 18:
        return "下午"
    if 18 <= h < 23:
        return "晚上"
    return "深夜"


def _split_lines(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in raw.split("\n")]
    return [ln for ln in lines if ln]


def _traceback_block(lines: list[str], max_lines: int) -> list[str]:
    if not lines or max_lines <= 0:
        return []
    start_idx = None
    for i, ln in enumerate(lines):
        if "Traceback (most recent call last)" in ln:
            start_idx = i
            break
    if start_idx is None:
        stack_patterns = [
            r'^\s*File\s+"[^"]+",\s+line\s+\d+',
            r"^\s*at\s+.+\(.+:\d+:\d+\)",
            r"stack trace",
            r"exception in thread",
        ]
        for i, ln in enumerate(lines):
            low = ln.lower()
            if any(re.search(p, ln) for p in stack_patterns[:-2]) or any(p in low for p in stack_patterns[-2:]):
                start_idx = i
                break
    if start_idx is None:
        return []
    out: list[str] = []
    for ln in lines[start_idx:]:
        out.append(ln)
        if len(out) >= max_lines:
            break
    return out


def _looks_like_code_line(line: str) -> float:
    ln = line.strip("\n")
    if not ln:
        return 0.0
    score = 0.0
    if re.search(r"^\s{2,}", line):
        score += 0.5
    if re.search(r"\b(def|class|import|from|return|if|elif|else|for|while|try|except|async|await|function|const|let|var)\b", ln):
        score += 1.0
    if re.search(r"[{}();<>]|==|!=|<=|>=|=>|::|->", ln):
        score += 0.8
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", ln):
        score += 0.6
    if re.search(r"^\s*#|^\s*//", ln):
        score += 0.4
    if re.search(r"^\s*```", ln):
        score += 0.8
    return score


def _code_block(lines: list[str], max_lines: int) -> list[str]:
    if not lines or max_lines <= 0:
        return []
    scores = [_looks_like_code_line(ln) for ln in lines]
    idxs = [i for i, s in enumerate(scores) if s >= 1.2]
    if not idxs:
        return []
    start = idxs[0]
    end = idxs[0]
    best_len = 1
    cur_start = idxs[0]
    cur_end = idxs[0]
    for i in idxs[1:]:
        if i == cur_end + 1:
            cur_end = i
        else:
            if cur_end - cur_start + 1 > best_len:
                best_len = cur_end - cur_start + 1
                start, end = cur_start, cur_end
            cur_start = i
            cur_end = i
    if cur_end - cur_start + 1 > best_len:
        start, end = cur_start, cur_end
    if best_len < 3:
        return []
    block = lines[start : end + 1]
    return block[:max_lines]


def _extract_entities(text: str, topk: int) -> list[str]:
    if topk <= 0:
        return []
    raw = text or ""
    entities: list[str] = []
    for m in re.finditer(r"https?://[^\s)]+", raw):
        entities.append(m.group(0)[:180])
    for m in re.finditer(r"\b[\w.-]+\.(com|cn|io|org|net|ai|dev|app)\b", raw, flags=re.I):
        entities.append(m.group(0))
    for m in re.finditer(r"(/[^\\s]+\\.[A-Za-z0-9]{1,6})", raw):
        entities.append(m.group(1)[:180])
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9_]*(Error|Exception)\b", raw):
        entities.append(m.group(0))
    out: list[str] = []
    seen = set()
    for e in entities:
        k = e.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
        if len(out) >= topk:
            break
    return out


def _extract_keywords(text: str, topk: int) -> list[str]:
    if topk <= 0:
        return []
    raw = (text or "").lower()
    tokens: list[str] = []
    tokens.extend(re.findall(r"[\\u4e00-\\u9fff]{2,}", raw))
    tokens.extend(re.findall(r"\b[a-z_][a-z0-9_]{2,}\b", raw))
    stop = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "your",
        "http",
        "https",
        "www",
        "com",
        "org",
        "net",
        "the",
        "and",
        "for",
        "are",
        "was",
        "you",
        "not",
        "but",
        "all",
        "any",
        "can",
        "use",
        "using",
        "into",
        "then",
        "when",
        "what",
        "why",
        "how",
        "have",
        "been",
        "will",
        "should",
        "could",
        "would",
        "true",
        "false",
        "null",
        "none",
    }
    freq = Counter([t for t in tokens if t and t not in stop and len(t) <= 40])
    out: list[str] = []
    for tok, _ in freq.most_common(topk):
        out.append(tok)
    return out


def _select_ui_lines(lines: list[str], max_lines: int) -> list[str]:
    if not lines or max_lines <= 0:
        return []
    scored: list[tuple[float, str]] = []
    for ln in lines:
        if len(ln) < 4 or len(ln) > 120:
            continue
        sym = sum(1 for ch in ln if ch in "{}();<>[]=+-/*\\|")
        ratio = sym / max(1, len(ln))
        if ratio > 0.25:
            continue
        score = 0.0
        if re.search(r"[\\u4e00-\\u9fff]", ln):
            score += 1.5
        if re.search(r"\b(button|menu|tab|settings|search|meeting|calendar)\b", ln, flags=re.I):
            score += 0.6
        if re.search(r"[:：•·\\-—]|\\b\\d{1,2}:\\d{2}\\b", ln):
            score += 0.3
        score += min(1.0, len(ln) / 80.0)
        scored.append((score, ln))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    seen = set()
    for _, ln in scored:
        if ln in seen:
            continue
        seen.add(ln)
        out.append(ln)
        if len(out) >= max_lines:
            break
    return out


@dataclass(frozen=True)
class MemoryCard:
    app: str
    scene: str
    actions: list[str]
    entities: list[str]
    keywords: list[str]
    ui_text: list[str]
    code: list[str]
    traceback: list[str]
    time_bucket: str
    embedding_text: str


def build_memory_card(
    *,
    app: str | None,
    title: str | None,
    timestamp: int | None,
    ocr_text: str | None,
    vision_description: str | None,
    ocr_kw_topk: int = 20,
    ui_text_max_lines: int = 6,
    code_max_lines: int = 30,
    traceback_max_lines: int = 25,
    max_chars: int = 2400,
) -> MemoryCard:
    desc_raw = (vision_description or "").strip()
    meta = _extract_first_json_object(desc_raw)
    app_val = (app or "").strip()
    title_val = (title or "").strip()
    if isinstance(meta, dict):
        if not app_val:
            v = meta.get("app")
            if isinstance(v, str):
                app_val = v.strip()
        if not title_val:
            v = meta.get("window_title")
            if isinstance(v, str):
                title_val = v.strip()
    scene = ""
    actions: list[str] = []
    entities_from_vl: list[str] = []
    desc_human = desc_raw
    if isinstance(meta, dict):
        v = meta.get("scene")
        if isinstance(v, str) and v.strip():
            scene = v.strip()
        v = meta.get("actions")
        if isinstance(v, list):
            actions = [str(x).strip() for x in v if str(x).strip()][:6]
        v = meta.get("entities")
        if isinstance(v, list):
            entities_from_vl = [str(x).strip() for x in v if str(x).strip()][:10]
        v = meta.get("description")
        if isinstance(v, str) and v.strip():
            desc_human = v.strip()
    if desc_human:
        scene = desc_human
    elif not scene and desc_raw:
        scene = desc_raw
    all_ocr = (ocr_text or "").strip()
    lines = _split_lines(all_ocr)
    tb = _traceback_block(lines, max_lines=traceback_max_lines)
    code = _code_block(lines, max_lines=code_max_lines)
    ui = _select_ui_lines(lines, max_lines=ui_text_max_lines)
    entities = []
    entities.extend(entities_from_vl)
    entities.extend(_extract_entities(all_ocr, topk=8))
    seen_ent = set()
    entities = [e for e in entities if not (e in seen_ent or seen_ent.add(e))]
    keywords = _extract_keywords(all_ocr + "\n" + desc_human, topk=ocr_kw_topk)
    tbucket = _time_bucket(timestamp)

    parts: list[str] = []
    if app_val:
        parts.append(f"[APP] {app_val}")
    if title_val and title_val != app_val:
        parts.append(f"[TITLE] {title_val}")
    if tbucket:
        parts.append(f"[TIME] {tbucket}")
    if scene:
        parts.append(f"[SCENE] {scene}")
    if actions:
        parts.append(f"[ACTION] {', '.join(actions)}")
    if entities:
        parts.append(f"[ENTITIES] {', '.join(entities[:10])}")
    if keywords:
        parts.append(f"[KEYWORDS] {', '.join(keywords[:ocr_kw_topk])}")
    if ui:
        parts.append("[UI_TEXT]")
        parts.extend(ui)
    if tb:
        parts.append("[TRACEBACK]")
        parts.extend(tb)
    if code:
        parts.append("[CODE]")
        parts.extend(code)
    embedding_text = "\n".join(parts).strip()
    if len(embedding_text) > max_chars:
        embedding_text = embedding_text[:max_chars].rstrip()

    return MemoryCard(
        app=app_val,
        scene=scene,
        actions=actions,
        entities=entities,
        keywords=keywords,
        ui_text=ui,
        code=code,
        traceback=tb,
        time_bucket=tbucket,
        embedding_text=embedding_text,
    )
