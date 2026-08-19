#!/usr/bin/env python3

import argparse

import numpy as np
import pandas as pd
import torch

from audio_editorial.models.importance import EditorialImportanceModel


DEFAULT_FEATURE_COLUMNS = [
    "importance",
    "emphasis",
    "novelty",
    "redundancy",
    "filler",
    "relative_loudness_z",
    "speech_rate",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    checkpoint = torch.load(
        args.checkpoint,
        map_location="cpu",
        weights_only=False,
    )

    feature_columns = checkpoint.get(
        "feature_columns",
        DEFAULT_FEATURE_COLUMNS,
    )
    labels = checkpoint.get(
        "labels",
        ["KEEP", "OPTIONAL", "CUT"],
    )

    df = pd.read_parquet(args.input).fillna(0)

    model = EditorialImportanceModel(
        input_dim=len(feature_columns),
        hidden_dim=256,
        num_classes=len(labels),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    x = torch.tensor(
        df[feature_columns].to_numpy(np.float32),
        dtype=torch.float32,
    )

    with torch.no_grad():
        prob = torch.softmax(model(x), dim=-1).cpu().numpy()

    for i, label in enumerate(labels):
        df[f"p_{label.lower()}"] = prob[:, i]

    pred_ids = prob.argmax(axis=1)
    df["pred_label"] = [labels[i] for i in pred_ids]

    df.to_parquet(args.output, index=False)


if __name__ == "__main__":
    main()
