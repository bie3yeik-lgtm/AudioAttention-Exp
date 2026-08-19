#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from audio_editorial.models.importance import EditorialImportanceModel


FEATURE_COLUMNS = [
    "importance",
    "emphasis",
    "novelty",
    "redundancy",
    "filler",
    "relative_loudness_z",
    "speech_rate",
]

LABELS = ["KEEP", "OPTIONAL", "CUT"]
LABEL_TO_ID = {v: i for i, v in enumerate(LABELS)}


def dataset(path: str):
    df = pd.read_parquet(path).fillna(0)

    x = torch.tensor(
        df[FEATURE_COLUMNS].to_numpy(np.float32),
        dtype=torch.float32,
    )

    label_col = (
        "editor_label"
        if "editor_label" in df.columns
        else "keep_recommendation"
    )

    y = torch.tensor(
        [LABEL_TO_ID[str(v)] for v in df[label_col]],
        dtype=torch.long,
    )

    return TensorDataset(x, y)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--train", required=True)
    parser.add_argument("--valid", required=True)
    parser.add_argument("--context-checkpoint")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)

    args = parser.parse_args()

    train_loader = DataLoader(
        dataset(args.train),
        batch_size=args.batch_size,
        shuffle=True,
    )

    valid_loader = DataLoader(
        dataset(args.valid),
        batch_size=args.batch_size,
    )

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    model = EditorialImportanceModel(
        input_dim=len(FEATURE_COLUMNS),
        hidden_dim=256,
    ).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
    )

    loss_fn = nn.CrossEntropyLoss()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    best = float("inf")

    for epoch in range(1, args.epochs + 1):
        model.train()

        for x, y in train_loader:
            x = x.to(device)
            y = y.to(device)

            logits = model(x)
            loss = loss_fn(logits, y)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        valid_loss = 0.0
        batches = 0

        with torch.no_grad():
            for x, y in valid_loader:
                x = x.to(device)
                y = y.to(device)

                loss = loss_fn(model(x), y)
                valid_loss += float(loss.item())
                batches += 1

        valid_loss /= max(batches, 1)

        checkpoint = {
            "model_state": model.state_dict(),
            "feature_columns": FEATURE_COLUMNS,
            "labels": LABELS,
        }

        torch.save(
            checkpoint,
            out_dir / f"epoch-{epoch:03d}.pt",
        )

        if valid_loss < best:
            best = valid_loss
            torch.save(
                checkpoint,
                out_dir / "best.pt",
            )

        print(
            f"epoch={epoch} valid_loss={valid_loss:.6f}"
        )


if __name__ == "__main__":
    main()
