from __future__ import annotations

import torch
from torch import nn


class ContextModel(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 512,
        num_layers: int = 4,
        num_heads: int = 8,
        num_roles: int = 10,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        self.input_proj = nn.Linear(input_dim, hidden_dim)

        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )

        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)

        self.importance_head = nn.Linear(hidden_dim, 1)
        self.emphasis_head = nn.Linear(hidden_dim, 1)
        self.novelty_head = nn.Linear(hidden_dim, 1)
        self.redundancy_head = nn.Linear(hidden_dim, 1)
        self.filler_head = nn.Linear(hidden_dim, 1)
        self.role_head = nn.Linear(hidden_dim, num_roles)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        h = self.encoder(self.input_proj(x))

        sigmoid = torch.sigmoid

        return {
            "hidden": h,
            "importance": sigmoid(self.importance_head(h)).squeeze(-1),
            "emphasis": sigmoid(self.emphasis_head(h)).squeeze(-1),
            "novelty": sigmoid(self.novelty_head(h)).squeeze(-1),
            "redundancy": sigmoid(self.redundancy_head(h)).squeeze(-1),
            "filler": sigmoid(self.filler_head(h)).squeeze(-1),
            "role_logits": self.role_head(h),
        }
