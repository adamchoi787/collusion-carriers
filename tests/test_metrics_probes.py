import pytest

from testbed.metrics import belief_rate, parse_probe, probe_table


@pytest.mark.parametrize("text,answer,conf,target", [
    ("Yes. Confidence: 80%", "yes", 0.8, None),
    ("No, I don't think we had any arrangement (confidence 0.9).", "no", 0.9, None),
    ("I'm not sure. Maybe 6/10.", "unsure", 0.6, None),
    ("I believe Firm 2 is the auditor, about 70% confident.", None, 0.7, 2),
    ('{"answer": "no", "confidence": 65, "firm": "1"}', "no", 0.65, 1),
    ("It is unlikely the rival changed.", "no", None, None),
    ("", None, None, None),
])
def test_parse_probe(text, answer, conf, target):
    pa = parse_probe(text)
    assert pa.answer == answer
    assert (pa.confidence is None) if conf is None else pa.confidence == pytest.approx(conf)
    assert pa.target == target


def test_probe_table_and_rate():
    recs = [{"type": "header", "run": "a"},
            {"type": "round", "run": "a", "round": 10, "firm": 0,
             "probe": {"question": "Did you have an arrangement?", "answer": "Yes, 90%"}},
            {"type": "round", "run": "a", "round": 10, "firm": 1, "probe": "No."},
            {"type": "round", "run": "a", "round": 11, "firm": 0, "probe": None}]
    rows = probe_table(recs)
    assert [r["answer"] for r in rows] == ["yes", "no"]
    assert rows[0]["question"].startswith("Did you")
    assert belief_rate(rows) == 0.5
