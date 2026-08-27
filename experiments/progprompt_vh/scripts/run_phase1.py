#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from experiments.progprompt_vh.adapters.llm_client import ModernLLMClient
from experiments.progprompt_vh.adapters.paths import EXPERIMENT_ROOT, RESULTS_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=EXPERIMENT_ROOT / "configs" / "benchmark.yaml",
    )
    parser.add_argument("--provider", choices=["primary", "fallback"], default="primary")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-tokens", type=int, default=32)
    args = parser.parse_args()
    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    spec = config["llm"][args.provider]
    spec = {
        **spec,
        "timeout_s": config["llm"]["primary"].get("timeout_s", 180),
        "wall_clock_timeout_s": config["llm"]["primary"].get(
            "wall_clock_timeout_s", 240
        ),
    }
    client = ModernLLMClient.from_env_spec(spec)
    call = client.generate(
        "Reply with exactly: HPAF_VH_OK",
        max_tokens=args.max_tokens,
        temperature=float(config["llm"]["temperature"]),
        seed=config["llm"].get("seed"),
    )
    record = call.to_dict()
    record["status"] = "passed" if "HPAF_VH_OK" in call.output_text else "failed"
    # The prompt/output and usage are research artifacts; the API key is never
    # placed in this structure.
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    output_path = args.output or RESULTS_ROOT / f"phase1_{args.provider}_llm_smoke.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if record["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
