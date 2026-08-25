"""CLI entrypoint for local SbD analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sbd_agent.graph import SbDAgent
from sbd_agent.models import ProjectRequest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Security-by-Design multi-agent analyzer")
    parser.add_argument("--input", type=Path, required=True, help="JSON ProjectRequest file")
    parser.add_argument("--prompt-version", default=None)
    parser.add_argument("--standards", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    request = ProjectRequest.model_validate_json(args.input.read_text(encoding="utf-8"))
    agent = SbDAgent(standards_dir=args.standards, prompt_version=args.prompt_version)
    result = agent.analyze(request)
    payload = result.model_dump()
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
