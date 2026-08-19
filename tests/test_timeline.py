import pandas as pd

from audio_editorial.models.timeline import build_timeline


def test_build_timeline_merges_adjacent_cut_segments():
    df = pd.DataFrame(
        [
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "p_keep": 0.1,
                "p_optional": 0.1,
                "p_cut": 0.8,
                "reason": "filler",
            },
            {
                "start_sec": 1.1,
                "end_sec": 2.0,
                "p_keep": 0.1,
                "p_optional": 0.1,
                "p_cut": 0.9,
                "reason": "filler",
            },
        ]
    )

    edits = build_timeline(df)

    assert len(edits) == 1
    assert edits[0]["action"] == "CUT"
    assert edits[0]["start"] == 0.0
    assert edits[0]["end"] == 2.0
