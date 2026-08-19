#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import urllib.request

from huggingface_hub import cancel_job


def cleanup(provider: str, resource_id: str, namespace: str | None = None) -> None:
    if provider == "runpod":
        req = urllib.request.Request(
            f"https://rest.runpod.io/v1/pods/{resource_id}",
            headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 204:
                raise RuntimeError(f"Unexpected Runpod status {resp.status}")
        return

    if provider == "vast":
        subprocess.run(
            [
                "vastai",
                "destroy",
                "instance",
                resource_id,
                "--api-key",
                os.environ["VAST_API_KEY"],
            ],
            check=True,
        )
        return

    if provider == "hf_jobs":
        # Completed jobs require no destructive cleanup. If still active when a
        # watchdog timeout occurs, cancel it.
        cancel_job(
            job_id=resource_id,
            namespace=namespace or None,
            token=os.environ.get("HF_TOKEN"),
        )
        return

    raise ValueError(provider)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", required=True)
    p.add_argument("--resource-id", required=True)
    p.add_argument("--namespace")
    args = p.parse_args()
    cleanup(args.provider, args.resource_id, args.namespace)


if __name__ == "__main__":
    main()
