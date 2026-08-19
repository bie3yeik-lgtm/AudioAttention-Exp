#!/usr/bin/env python3

import json
import platform
import sys

report = {
    "python": sys.version,
    "platform": platform.platform(),
}

try:
    import torch
    report["torch"] = torch.__version__
    report["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        report["gpu"] = torch.cuda.get_device_name(0)
except Exception as exc:
    report["torch_error"] = repr(exc)

try:
    import transformers
    report["transformers"] = transformers.__version__
except Exception as exc:
    report["transformers_error"] = repr(exc)

try:
    import nemo
    report["nemo"] = getattr(nemo, "__version__", "unknown")
except Exception as exc:
    report["nemo_error"] = repr(exc)

print(json.dumps(report, ensure_ascii=False, indent=2))
