"""Unit tests verifying TypeScript SDK structure and exports."""

import json
import os


def test_typescript_sdk_files_exist():
    sdk_dir = os.path.join(os.path.dirname(__file__), "..", "packages", "sdk-ts")
    assert os.path.exists(os.path.join(sdk_dir, "package.json"))
    assert os.path.exists(os.path.join(sdk_dir, "tsconfig.json"))
    assert os.path.exists(os.path.join(sdk_dir, "src", "index.ts"))

    with open(os.path.join(sdk_dir, "package.json"), "r", encoding="utf-8") as f:
        pkg = json.load(f)
        assert pkg["name"] == "@agentready/sdk"

    with open(os.path.join(sdk_dir, "src", "index.ts"), "r", encoding="utf-8") as f:
        code = f.read()
        assert "export class AgentReadyClient" in code
        assert "public async scan" in code
        assert "public getBadgeUrl" in code
