#!/usr/bin/env python3

import argparse

import pandas as pd

from audio_editorial.teacher.stepaudio import StepAudioTeacher


def _context_text(df, idx: int, radius: int = 2) -> tuple[str, str]:
    left = df.iloc[max(0, idx - radius):idx]
    right = df.iloc[idx + 1: idx + 1 + radius]

    previous = "\n".join(left["text"].astype(str).tolist())
    next_ = "\n".join(right["text"].astype(str).tolist())

    return previous, next_


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--audio", required=True)
    parser.add_argument("--segments", required=True)
    parser.add_argument("--output", required=True)

    parser.add_argument(
        "--model",
        default="stepfun-ai/Step-Audio-2-mini",
    )

    parser.add_argument(
        "--global-summary",
        default="",
    )

    args = parser.parse_args()

    df = pd.read_parquet(args.segments)

    teacher = StepAudioTeacher(args.model)

    rows = []

    for idx, row in df.iterrows():
        previous, next_ = _context_text(df, idx)

        label = teacher.analyze(
            audio_path=args.audio,
            segment_id=str(row["segment_id"]),
            transcript=str(row["text"]),
            previous_context=previous,
            next_context=next_,
            global_summary=args.global_summary,
        )

        rows.append(label.model_dump())

    pd.DataFrame(rows).to_parquet(
        args.output,
        index=False,
    )


if __name__ == "__main__":
    main()
