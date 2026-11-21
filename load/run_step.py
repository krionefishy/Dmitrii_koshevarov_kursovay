from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def compose_container(service: str) -> str:
    command = [
        "docker",
        "compose",
        "--env-file",
        ".env",
        "-f",
        "deploy/compose.yaml",
        "-f",
        "deploy/compose.benchmark.yaml",
        "ps",
        "-q",
        service,
    ]
    container = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    if not container:
        raise RuntimeError(f"Compose service {service} is not running")
    return container


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["mixed", "heavy"])
    parser.add_argument("rate", type=int)
    parser.add_argument("--duration-seconds", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.scenario}-{args.rate:04d}rps"
    summary = args.output_dir / f"{stem}-summary.json"
    resources = args.output_dir / f"{stem}-resources.csv"
    log = args.output_dir / f"{stem}-k6.log"

    backend = compose_container("backend")
    database = compose_container("db")
    collector_command = [
        sys.executable,
        "load/collect_resources.py",
        "--backend-container",
        backend,
        "--db-container",
        database,
        "--duration",
        str(args.duration_seconds + 7),
        "--output",
        str(resources),
    ]
    collector = subprocess.Popen(collector_command)
    environment = os.environ.copy()
    environment.update(
        {
            "SCENARIO": args.scenario,
            "RATE": str(args.rate),
            "DURATION": f"{args.duration_seconds}s",
            "BASE_URL": args.base_url,
            "SUMMARY_PATH": str(summary),
        }
    )
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                ["k6", "run", "--quiet", "load/helpdesk.js"],
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
    finally:
        collector.wait(timeout=args.duration_seconds + 20)

    if result.returncode not in (0, 99):
        raise SystemExit(result.returncode)
    print(summary)


if __name__ == "__main__":
    main()
