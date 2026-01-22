from openrecall.server.fusion import rrf_fuse


def test_rrf_fuse_orders_reasonably():
    vec = [1, 2, 3]
    fts = [3, 2, 4]
    fused = rrf_fuse([vec, fts], k=60)
    ids = [i for i, _ in fused]
    assert ids[0] in {2, 3}
    assert 2 in ids
    assert 3 in ids
    assert 1 in ids
    assert 4 in ids


def test_rrf_fuse_handles_empty_lists():
    fused = rrf_fuse([[], []], k=60)
    assert fused == []
