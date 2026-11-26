"""Validate all sealed phases and write finite submission result and cost indices."""

from __future__ import annotations

import argparse
from pathlib import Path

from routebench.submission.analysis import aggregate
from routebench.submission.protocol import load_protocol


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = load_protocol(args.manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    report = aggregate(protocol, args.runs, args.output)
    print(report["status"])


if __name__ == "__main__":
    main()
