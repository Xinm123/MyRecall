from __future__ import annotations


def rrf_fuse(
    ranked_lists: list[list[int]],
    k: int = 60,
    topk: int | None = None,
) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    kk = float(k)
    for ranks in ranked_lists:
        for idx, doc_id in enumerate(ranks):
            rank = float(idx + 1)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (kk + rank)
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if topk is not None:
        return items[: int(topk)]
    return items
