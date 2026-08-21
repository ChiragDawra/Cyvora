#!/usr/bin/env python3
"""Fails if a Terraform variable with no default isn't passed by the deploy workflow.

This exists because it already happened: the OTX feed added a required `otx_api_key`
variable and nothing wired it into .github/workflows/deploy.yml, so every automatic
apply on main would have failed with "No value for required variable". Nobody noticed,
because the feed had been deployed by hand from a local shell where run.sh exports it.

A variable with a default degrades quietly when forgotten; one without a default breaks
the whole deploy. Only the latter is checked here.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VARIABLES_TF = REPO_ROOT / "infra" / "variables.tf"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# Splits variables.tf into one block per `variable "name" { ... }`, non-greedily up to the
# first line that closes at column 0 - matching how terraform fmt lays the file out.
_VARIABLE_BLOCK = re.compile(r'^variable\s+"([^"]+)"\s*\{(.*?)^\}', re.DOTALL | re.MULTILINE)


def required_variables(source: str) -> list[str]:
    return [
        name
        for name, body in _VARIABLE_BLOCK.findall(source)
        if not re.search(r"^\s*default\s*=", body, re.MULTILINE)
    ]


def main() -> int:
    required = required_variables(VARIABLES_TF.read_text())
    workflow = DEPLOY_WORKFLOW.read_text()

    missing = [name for name in required if f"TF_VAR_{name}:" not in workflow]
    if missing:
        print(
            f"{DEPLOY_WORKFLOW.relative_to(REPO_ROOT)} does not pass every required "
            f"variable from {VARIABLES_TF.relative_to(REPO_ROOT)}:",
            file=sys.stderr,
        )
        for name in missing:
            print(f"  missing: TF_VAR_{name}", file=sys.stderr)
        print(
            "\nAdd it under the Terraform apply step's `env:`, sourced from a repository "
            "secret, and list that secret in the workflow's header comment.",
            file=sys.stderr,
        )
        return 1

    print(f"deploy.yml passes all {len(required)} required variables: {', '.join(required)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
