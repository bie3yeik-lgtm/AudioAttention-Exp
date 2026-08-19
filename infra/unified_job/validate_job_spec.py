#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

import jsonschema


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--schema", default="schemas/job-spec.schema.json")
    p.add_argument("job_spec")
    args = p.parse_args()

    with open(args.schema, "r", encoding="utf-8") as f:
        schema = json.load(f)

    with open(args.job_spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    jsonschema.Draft202012Validator(schema).validate(spec)
    print(json.dumps(spec, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
