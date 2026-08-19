#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pod_id")
    args = parser.parse_args()

    req = urllib.request.Request(
        f"https://rest.runpod.io/v1/pods/{args.pod_id}",
        headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status != 204:
            raise SystemExit(f"Unexpected status: {resp.status}")


if __name__ == "__main__":
    main()
