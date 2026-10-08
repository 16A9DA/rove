from __future__ import annotations

import argparse
import json

from .pipeline import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Load an AgentNet subset, normalize its actions, and print stats.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--source", choices=["ubuntu", "win_mac"], default="ubuntu")
    args = parser.parse_args()

    report = run_evaluation(limit=args.limit, source=args.source)
    print(json.dumps(report.stats.to_dict(), indent=2))


if __name__ == "__main__":
    main()
