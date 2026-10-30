#!/usr/bin/env python3
"""Copies results/*.json into docs/data/ and writes the machine index."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    out = ROOT / "docs" / "data"
    out.mkdir(parents=True, exist_ok=True)
    machines = []
    for f in sorted((ROOT / "results").glob("*.json")):
        data = json.loads(f.read_text())
        shutil.copyfile(f, out / f.name)
        arch = data["machine"]["machine"]
        label = {"x86_64": "x86-64", "aarch64": "arm64"}.get(arch, arch)
        machines.append({"id": f.stem, "file": f.name, "label": f"{label}: {data['title']}"})
    # x86-64 first, like the README.
    machines.sort(key=lambda m: (not m["label"].startswith("x86"), m["id"]))
    (out / "index.json").write_text(json.dumps({"machines": machines}, indent=1) + "\n")
    print(f"{len(machines)} machines -> {out}")


if __name__ == "__main__":
    main()
