#!/usr/bin/env python3

import argparse

from audio_editorial.asr.parakeet import transcribe_audio


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--model",
        default="nvidia/parakeet-tdt_ctc-0.6b-ja",
    )
    parser.add_argument("--session-id")
    args = parser.parse_args()

    df = transcribe_audio(
        audio_path=args.audio,
        model_id=args.model,
        session_id=args.session_id,
    )
    df.to_parquet(args.output, index=False)


if __name__ == "__main__":
    main()
