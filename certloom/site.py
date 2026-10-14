"""Build a static consumer lab using the installed source-bearing resources."""

import json
from hashlib import sha256
from pathlib import Path

from .artifact import asset_directory, checker_source


def build(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    entries = []

    def put(name, data):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        entries.append(
            {"path": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
        )

    for name in ("web", "examples", "docs"):
        for item in sorted(asset_directory(name).rglob("*")):
            if item.is_file() and (name != "docs" or item.suffix in (".html", ".css")):
                path = item.relative_to(asset_directory(name)).as_posix()
                put(path if name == "web" else name + "/" + path, item.read_bytes())
    put("checker.py", checker_source().encode())
    put("LICENSE.txt", asset_directory("licenses").joinpath("LICENSE").read_bytes())
    put(
        "README.txt",
        b"Certloom browser lab\nServe these files using localhost HTTP or HTTPS. Computation uses local BigInt arithmetic in a Web Worker; there is no CDN or computation service. file:// workers are unsupported. Original examples are declared mathematical equations, not hardware measurements. Python checker artifacts verify the same input independently using only the standard library. Sources: https://github.com/nazeeh111/Certloom\n",
    )
    manifest = {"version": 1, "files": entries}
    with (destination / "source-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest
