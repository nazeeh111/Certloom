"""Source-bearing artifacts; no solver or uploaded executable code required."""

import json
import zipfile
from hashlib import sha256
from pathlib import Path

from .engine import MAX_BYTES, VerificationError, verify_text


def read_certificate(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise VerificationError("Certificate exceeds the 2 MiB limit.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationError("Certificate must be UTF-8 JSON.") from error


def checker_source():
    """Exact engine source plus a bounded, ordinary standalone entry point."""
    source = Path(__file__).with_name("engine.py").read_text()
    license_text = asset_directory("licenses").joinpath("LICENSE").read_text()
    source += "\n\n# Created with Certloom: https://github.com/nazeeh111/Certloom\n"
    source += "\n".join("# " + line for line in license_text.splitlines()) + "\n"
    source += """
if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import sys
    parser = argparse.ArgumentParser(description="Verify an exact stored-system numerical certificate.")
    parser.add_argument("certificate")
    args = parser.parse_args()
    try:
        with Path(args.certificate).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise VerificationError("Certificate exceeds the 2 MiB limit.")
        result = verify_text(raw.decode("utf-8"))
        print(json.dumps(result, indent=2))
        if result["status"] != "certified":
            raise SystemExit(3)
    except (VerificationError, OSError, UnicodeError) as error:
        print("Verification refused: " + str(error), file=sys.stderr)
        raise SystemExit(2)
"""
    return source


def asset_directory(name):
    package = Path(__file__).resolve().parent
    if (package / name).is_dir():
        return package / name
    if name == "licenses":
        return package.parent
    return package.parent / name


def bundle_members(text):
    result = verify_text(text)
    certificate = text.encode("utf-8")
    receipt = {
        "format": "certloom-verification-v1",
        "certificate_sha256": sha256(certificate).hexdigest(),
        "scope": "Exact stored binary64 linear system; identity is not authenticity.",
        "result": result,
    }
    files = {
        "certificate.json": certificate,
        "checker.py": checker_source().encode("utf-8"),
        "verification.json": (json.dumps(receipt, indent=2) + "\n").encode(),
        "README.txt": b"Certloom numerical result artifact\n\nRun python3 -I -S checker.py certificate.json. Only the Python standard library is needed. Compare the checker output with the result field of verification.json. Exit 0 means an enclosure is certified, 3 means the proof premise failed, 2 means invalid input or a file error. The checker recomputes the claim from the stored matrix, right-hand side, proposed answer and approximate inverse. A wide valid enclosure is not necessarily an accurate answer; threshold decisions are separate. This checks the exact represented binary64 equations, not physical model truth, measurements or producer authenticity. Source and method: https://github.com/nazeeh111/Certloom .\n",
    }
    files["SHA256SUMS"] = "".join(
        sha256(data).hexdigest() + "  " + name + "\n"
        for name, data in sorted(files.items())
    ).encode()
    return files


def write_bundle(text, destination):
    files = bundle_members(text)  # Verify before opening the output.
    with (
        Path(destination).open("xb") as stream,
        zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return {
        "out": str(destination),
        "members": len(files),
        "sha256": sha256(Path(destination).read_bytes()).hexdigest(),
    }
