#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from audio_editorial.models.context import ContextModel


FEATURE_COLUMNS = [
    "rms_db",
    "peak_db",
    "pitch_mean",
    "pitch_std",
    "spectral_centroid",
    "spectral_bandwidth",
    "speech_rate",
    "relative_loudness_z",
]

ROLE_NAMES = [
    "question",
    "answer",
    "explanation",
    "example",
    "summary",
    "transition",
    "filler",
    "repetition",
    "digression",
    "other",
]

ROLE_TO_ID = {name: i for i, name in enumerate(ROLE_NAMES)}


def make_dataset(path: str):
    df = pd.read_parquet(path).fillna(0)

    x = torch.tensor(
        df[FEATURE_COLUMNS].to_numpy(np.float32),
        dtype=torch.float32,
    ).unsqueeze(1)

    importance = torch.tensor(
        df["importance"].to_numpy(np.float32)
    ).unsqueeze(1)

    role = torch.tensor(
        [ROLE_TO_ID.get(str(v), ROLE_TO_ID["other"]) for v in df["dialogue_role"]],
        dtype=torch.long,
    ).unsqueeze(1)

    return df, TensorDataset(x, importance, role)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--valid", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    args = parser.parse_args()

    _, train_ds = make_dataset(args.train)
    _, valid_ds = make_dataset(args.valid)

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
    )

    valid_loader = DataLoader(
        valid_ds,
        batch_size=args.batch_size,
    )

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    model = ContextModel(
        input_dim=len(FEATURE_COLUMNS),
        hidden_dim=256,
        num_layers=2,
        num_heads=4,
        num_roles=len(ROLE_NAMES),
    ).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
    )

    mse = nn.MSELoss()
    ce = nn.CrossEntropyLoss()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    best = float("inf")

    for epoch in range(1, args.epochs + 1):
        model.train()

        for x, importance, role in train_loader:
            x = x.to(device)
            importance = importance.to(device)
            role = role.to(device)

            output = model(x)

            loss = (
                mse(output["importance"], importance)
                + ce(
                    output["role_logits"].reshape(-1, len(ROLE_NAMES)),
                    role.reshape(-1),
                )
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        valid_loss = 0.0
        batches = 0

        with torch.no_grad():
            for x, importance, role in valid_loader:
                x = x.to(device)
                importance = importance.to(device)
                role = role.to(device)

                output = model(x)

                loss = (
                    mse(output["importance"], importance)
                    + ce(
                        output["role_logits"].reshape(-1, len(ROLE_NAMES)),
                        role.reshape(-1),
                    )
                )

                valid_loss += float(loss.item())
                batches += 1

        valid_loss /= max(batches, 1)

        checkpoint = {
            "model_state": model.state_dict(),
            "feature_columns": FEATURE_COLUMNS,
            "role_names": ROLE_NAMES,
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
