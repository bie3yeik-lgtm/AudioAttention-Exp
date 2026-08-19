from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_requirements_paths_in_workflows_exist():
    pattern = re.compile(r"pip install(?:\s+--\S+)*\s+-r\s+([^\s]+)")
    missing = []
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = pattern.search(line.strip())
            if not m:
                continue
            raw = m.group(1).strip("'\"")
            if "$" in raw or "${{" in raw:
                continue
            if not (ROOT / raw).exists():
                missing.append((wf.name, raw))
    assert not missing, f"Missing requirements paths: {missing}"



def test_budgeted_unified_job_resolves_job_kind_before_writing_github_env():
    text = (ROOT / ".github/workflows/budgeted-unified-job.yml").read_text()
    assert "job_kind=\"$(jq -r '.runtime_env.JOB_KIND // .workload'" in text
    assert 'for key in JOB_KIND AUDIO_REL' not in text
    assert 'if [ -z "${JOB_KIND:-}" ]' not in text
