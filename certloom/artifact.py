"""Source-bearing artifacts; no solver or uploaded executable code required."""

import json
import stat
import zipfile
import zlib
from hashlib import sha256
from pathlib import Path

from .engine import MAX_BYTES, VerificationError, verify_text
from .publication import fresh_output


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
    source += "\n\n# Created with Enclose: https://github.com/nazeeh111/Certloom\n"
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
        "LICENSE-FIPY.txt": asset_directory("examples")
        .joinpath("FIPY-TERMS.txt")
        .read_bytes(),
        "verification.json": (json.dumps(receipt, indent=2) + "\n").encode(),
        "README.txt": b"Certloom numerical result artifact\n\nWith a separately installed trusted Certloom, run certloom verify-bundle on the ZIP. The bundled checker is not executed. If you choose to run the extracted checker.py, first establish trust in that file, then run python3 -I -S checker.py certificate.json and compare its output with verification.json. Checksums identify bytes, not authorship. Exit 0 means an enclosure is certified, 3 means the proof premise failed, 2 means invalid input or a file error. The checker recomputes the claim from the stored matrix, right-hand side, proposed answer and proof witness (positive weights for sparse mode, approximate inverse for dense mode). A wide valid enclosure is not necessarily an accurate answer; threshold decisions are separate. This checks the exact represented binary64 equations, not physical model truth, measurements or producer authenticity. Source and method: https://github.com/nazeeh111/Certloom .\n",
    }
    files["SHA256SUMS"] = "".join(
        sha256(data).hexdigest() + "  " + name + "\n"
        for name, data in sorted(files.items())
    ).encode()
    return files


def write_bundle(text, destination):
    files = bundle_members(text)  # Verify before opening the output.
    with (
        fresh_output(destination) as stream,
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


MEMBER_NAMES = frozenset({"certificate.json", "checker.py", "LICENSE-FIPY.txt",
                          "verification.json", "README.txt", "SHA256SUMS"})
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 6 * 1024 * 1024
SCOPE = "Exact stored binary64 linear system; identity is not authenticity."


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("Duplicate receipt key.")
        result[key] = value
    return result


def verify_bundle(path):
    """Admit bounded source-bearing ZIP data and recompute with the installed engine."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_ARCHIVE_BYTES + 1)
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise VerificationError("Bundle exceeds the archive size limit.")
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = {i.filename for i in infos}
            legacy = MEMBER_NAMES - {"SHA256SUMS"}
            if not ((len(infos) == 6 and names == MEMBER_NAMES) or (len(infos) == 5 and names == legacy)):
                raise VerificationError("Bundle must contain exactly a supported five- or six-member set.")
            total = 0
            for info in infos:
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (info.orig_filename != info.filename or info.is_dir() or
                    (info.external_attr & 0x10) or kind not in (0, stat.S_IFREG) or
                    info.flag_bits & (1 | 64 | 8192) or
                    info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise VerificationError("Unsupported bundle member metadata.")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise VerificationError("Bundle member exceeds the size limit.")
                total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise VerificationError("Bundle contents exceed the size limit.")
            files = {}
            for info in infos:
                with archive.open(info) as member:
                    value = member.read(MAX_MEMBER_BYTES + 1)
                if len(value) != info.file_size or len(value) > MAX_MEMBER_BYTES:
                    raise VerificationError("Bundle member length mismatch.")
                files[info.filename] = value
        expected = "".join(sha256(files[name]).hexdigest() + "  " + name + "\n"
                           for name in sorted(MEMBER_NAMES - {"SHA256SUMS"})).encode()
        if "SHA256SUMS" in files and files["SHA256SUMS"] != expected:
            raise VerificationError("Bundle checksum list or member digest mismatch.")
        if files["checker.py"] != checker_source().encode("utf-8"):
            raise VerificationError("Bundled checker differs from this trusted installation.")
        receipt = json.loads(files["verification.json"].decode("utf-8"),
                             object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(VerificationError("Nonfinite receipt value.")))
        if not isinstance(receipt, dict) or set(receipt) != {"format", "certificate_sha256", "scope", "result"}:
            raise VerificationError("Invalid verification receipt.")
        if (receipt["format"] != "certloom-verification-v1" or receipt["scope"] != SCOPE or
            receipt["certificate_sha256"] != sha256(files["certificate.json"]).hexdigest()):
            raise VerificationError("Receipt identity or scope mismatch.")
        result = verify_text(files["certificate.json"].decode("utf-8"))
        if json.dumps(receipt["result"], sort_keys=True, allow_nan=False) != json.dumps(result, sort_keys=True, allow_nan=False):
            raise VerificationError("Receipt result disagrees with trusted recomputation.")
        return {"checksums": "verified" if "SHA256SUMS" in files else "absent",
                "checker": "matches-installed", "result": result,
                "scope": "Byte consistency is not producer authentication."}
    except (zipfile.BadZipFile, EOFError, UnicodeError, ValueError, RecursionError, zlib.error, RuntimeError, NotImplementedError) as error:
        raise VerificationError("Invalid or unsupported bundle: " + str(error)) from error
