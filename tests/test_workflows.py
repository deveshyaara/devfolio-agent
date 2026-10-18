from pathlib import Path

import yaml


def test_workflow_structure_and_least_privilege():
    workflow = yaml.safe_load(Path(".github/workflows/sync.yml").read_text())
    # YAML 1.1 parses the GitHub 'on' key as True; support either representation.
    triggers = workflow.get("on", workflow.get(True))
    assert "schedule" in triggers and "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    steps = workflow["jobs"]["sync"]["steps"]
    command = next(s for s in steps if s.get("name") == "Incremental synchronization")
    assert "python -m devfolio.sync" in command["run"]
    assert "${{ secrets.SUPABASE_SYNC_DB_URL }}" == command["env"]["SUPABASE_SYNC_DB_URL"]
    assert command["env"]["GITHUB_USERNAME"] == "${{ vars.PORTFOLIO_GITHUB_USERNAME }}"
    assert "--allow-empty" not in command["run"]
    assert any(s.get("if") == "always()" and "upload-artifact" in s.get("uses", "") for s in steps)
