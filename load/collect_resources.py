from __future__ import annotations

import argparse
import csv
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

MEMORY_UNITS = {
    "B": 1 / (1024 * 1024),
    "kB": 1 / 1024,
    "KiB": 1 / 1024,
    "MB": 1,
    "MiB": 1,
    "GB": 1024,
    "GiB": 1024,
}


def run(*command: str) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def memory_mib(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9.]+)\s*([A-Za-z]+)\s*", value)
    if not match:
        raise ValueError(f"Unsupported memory value: {value}")
    return float(match.group(1)) * MEMORY_UNITS[match.group(2)]


def containers_stats(*containers: str) -> dict[str, tuple[float, float, float]]:
    raw = run(
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{.Container}}|{{.CPUPerc}}|{{.MemUsage}}",
        *containers,
    )
    result: dict[str, tuple[float, float, float]] = {}
    for line in raw.splitlines():
        container, cpu, memory = line.split("|", 2)
        used, limit = (part.strip() for part in memory.split("/", 1))
        result[container] = (float(cpu.rstrip("%")), memory_mib(used), memory_mib(limit))
    return result


def pg_connections(container: str, user: str, database: str) -> tuple[int, int]:
    query = (
        "SELECT count(*), count(*) FILTER (WHERE state='active') "
        "FROM pg_stat_activity WHERE datname=current_database();"
    )
    raw = run("docker", "exec", container, "psql", "-U", user, "-d", database, "-Atc", query)
    total, active = raw.split("|", 1)
    return int(total), int(active)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-container", required=True)
    parser.add_argument("--db-container", required=True)
    parser.add_argument("--db-user", default="app")
    parser.add_argument("--db-name", default="dmitrii_koshevarov_helpdesk")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp_utc",
        "elapsed_s",
        "app_cpu_pct",
        "app_memory_mib",
        "app_memory_limit_mib",
        "db_cpu_pct",
        "db_memory_mib",
        "db_memory_limit_mib",
        "pg_connections_total",
        "pg_connections_active",
    ]
    started = time.monotonic()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        while time.monotonic() - started <= args.duration:
            iteration_started = time.monotonic()
            stats = containers_stats(args.backend_container, args.db_container)
            app_cpu, app_memory, app_limit = stats[args.backend_container]
            db_cpu, db_memory, db_limit = stats[args.db_container]
            total, active = pg_connections(args.db_container, args.db_user, args.db_name)
            writer.writerow(
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "elapsed_s": f"{time.monotonic() - started:.3f}",
                    "app_cpu_pct": f"{app_cpu:.2f}",
                    "app_memory_mib": f"{app_memory:.2f}",
                    "app_memory_limit_mib": f"{app_limit:.2f}",
                    "db_cpu_pct": f"{db_cpu:.2f}",
                    "db_memory_mib": f"{db_memory:.2f}",
                    "db_memory_limit_mib": f"{db_limit:.2f}",
                    "pg_connections_total": total,
                    "pg_connections_active": active,
                }
            )
            stream.flush()
            time.sleep(max(0.0, args.interval - (time.monotonic() - iteration_started)))


if __name__ == "__main__":
    main()
