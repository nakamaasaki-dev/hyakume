from hyakume.aggregate import aggregate, normalize_url, topic_counts
from hyakume.models import CollectedItem


def test_normalize_url_strips_tracking_and_scheme():
    a = normalize_url("http://www.example.com/a/b/?utm_source=x&id=1")
    b = normalize_url("https://example.com/a/b?id=1")
    assert a == b == "https://example.com/a/b?id=1"


def test_aggregate_merges_by_url_and_counts_reach():
    items = [
        CollectedItem(persona_id="p1", title="A", url="https://x.com/1", summary="s", interest=5,
                      why_it_matters="r1", topics=["t1"]),
        CollectedItem(persona_id="p2", title="A", url="http://www.x.com/1/", summary="longer s",
                      interest=3, why_it_matters="r2", topics=["t2"]),
        CollectedItem(persona_id="p1", title="B", url="https://x.com/2", summary="s", interest=2),
    ]
    agg = aggregate(items)
    assert [a.title for a in agg] == ["A", "B"]
    top = agg[0]
    assert top.reach == 2
    assert top.seen_by == ["p1", "p2"]
    assert top.avg_interest == 4.0
    assert top.summary == "longer s"
    assert top.topics == ["t1", "t2"]
    assert top.reasons == ["r1", "r2"]
    assert topic_counts(agg)[0] in [("t1", 2), ("t2", 2)]
