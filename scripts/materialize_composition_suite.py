"""Materialize fixed matched pairs from explicit catalog-backed authoring choices."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml

from routebench.defense.contracts import content_hash
from routebench.submission.common import durable_json
from routebench.submission.composition import audit_pair, load_pair, materialize_family


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--spec", type=Path, default=Path("configs/submission/composition-families.yaml")
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    spec = yaml.safe_load((root / args.spec).read_text())
    families = spec["families"]
    counts = Counter(family["split"] for family in families)
    if counts != {"test": 20, "development": 4} or len({f["id"] for f in families}) != 24:
        raise ValueError(
            "the fixed composition allocation must contain 20 test and 4 development families"
        )
    rows = []
    for ordinal, family in enumerate(families):
        for kind in ("dependency", "order"):
            path = materialize_family(root, spec, family, kind, ordinal)
            rows.append(audit_pair(load_pair(path)))
    durable_json(
        args.report,
        {
            "status": "complete",
            "authoring_spec_digest": content_hash(spec),
            "families": dict(counts),
            "pairs": len(rows),
            "source_checks": rows,
            "review_scope": "automated source/replay/matching/public-projection checks",
            "independent_human_review_claimed": False,
        },
    )
    print(f"Materialized and audited {len(rows)} pairs across {len(families)} families")


if __name__ == "__main__":
    main()
