"""Build deterministic, source-bearing releases using only the standard library."""

import argparse
import base64
import csv
import io
import json
import re
import stat
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from email.policy import default
from hashlib import sha256
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from certloom import __version__  # noqa: E402
from certloom.artifact import bundle_members  # noqa: E402
from certloom.site import build as build_site  # noqa: E402

DATE = (2026, 10, 13, 0, 0, 0)
SKIP = {
    "__pycache__",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}
PUBLIC_ROOT_FILES = (
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "pyproject.toml",
    "setup.py",
)
PUBLIC_DIRS = ("certloom", "scripts", "tests", "web", "examples", "docs", ".github")


def safe_name(name):
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or str(path) != name
        or "\\" in name
        or any(part in ("", ".", "..") for part in path.parts)
        or any(ord(char) < 32 for char in name)
    ):
        raise ValueError("Unsafe archive name: " + repr(name))
    return name


def selected_files(directory):
    files = {}
    if directory.is_symlink():
        raise ValueError("Symlink source directory refused: " + str(directory))
    for source in sorted(directory.rglob("*")):
        relative = source.relative_to(directory)
        if any(part in SKIP or part.startswith("._") for part in relative.parts):
            continue
        if source.name == ".DS_Store" or source.suffix in (".pyc", ".pyo"):
            continue
        if source.is_symlink():
            raise ValueError("Symlink source member refused: " + str(source))
        if source.is_file():
            files[safe_name(relative.as_posix())] = source.read_bytes()
    return files


def write_archive(path, members):
    normalized = {}
    for name, data in sorted(members.items()):
        safe_name(name)
        if name.casefold() in normalized:
            raise ValueError("Duplicate archive member: " + name)
        if not isinstance(data, bytes):
            raise TypeError("Archive contents must be bytes.")
        normalized[name.casefold()] = name
    with (
        Path(path).open("xb") as stream,
        zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as archive,
    ):
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, DATE)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC validation failed.")
        if len(archive.infolist()) != len(members):
            raise ValueError("Archive member count differs.")
        for entry in archive.infolist():
            safe_name(entry.filename)
            if not stat.S_ISREG(entry.external_attr >> 16):
                raise ValueError("Non-regular archive member.")
            if archive.read(entry) != members[entry.filename]:
                raise ValueError("Archive bytes differ: " + entry.filename)


def wheel_members():
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if not re.search(
        r'^version\s*=\s*"' + re.escape(__version__) + r'"\s*$',
        project_text,
        re.MULTILINE,
    ):
        raise ValueError("Package and pyproject versions disagree.")
    members = {
        "certloom/" + name: data
        for name, data in selected_files(ROOT / "certloom").items()
    }
    for resource in ("web", "examples", "docs"):
        members.update(
            {
                "certloom/" + resource + "/" + name: data
                for name, data in selected_files(ROOT / resource).items()
            }
        )
    license_data = (ROOT / "LICENSE").read_bytes()
    members["certloom/licenses/LICENSE"] = license_data
    dist_info = "certloom-" + __version__ + ".dist-info/"
    members[dist_info + "METADATA"] = (
        "Metadata-Version: 2.4\nName: certloom\nVersion: "
        + __version__
        + "\nSummary: Numerical results with portable, exactly checked error bounds"
        + "\nRequires-Python: >=3.10\nLicense-Expression: MIT\nLicense-File: LICENSE"
        + "\nProject-URL: Source, https://github.com/nazeeh111/Certloom"
        + "\nDescription-Content-Type: text/markdown\n\n"
        + (ROOT / "README.md").read_text(encoding="utf-8")
    ).encode("utf-8")
    members[dist_info + "WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: certloom-stdlib-packager\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    members[dist_info + "entry_points.txt"] = (
        b"[console_scripts]\ncertloom = certloom.cli:main\n"
    )
    members[dist_info + "licenses/LICENSE"] = license_data
    metadata = BytesParser(policy=default).parsebytes(members[dist_info + "METADATA"])
    license_files = metadata.get_all("License-File", [])
    if not license_files:
        raise ValueError("Wheel metadata has no license file.")
    for license_file in license_files:
        safe_name(license_file)
        if members.get(dist_info + "licenses/" + license_file) != license_data:
            raise ValueError(
                "License metadata does not resolve to the MIT license bytes."
            )
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(members.items()):
        digest = (
            base64.urlsafe_b64encode(sha256(data).digest()).rstrip(b"=").decode("ascii")
        )
        writer.writerow([name, "sha256=" + digest, str(len(data))])
    writer.writerow([dist_info + "RECORD", "", ""])
    members[dist_info + "RECORD"] = record.getvalue().encode("utf-8")
    return members


def source_members():
    prefix = "certloom-" + __version__ + "/"
    members = {prefix + name: (ROOT / name).read_bytes() for name in PUBLIC_ROOT_FILES}
    for directory in PUBLIC_DIRS:
        if (ROOT / directory).is_dir():
            members.update(
                {
                    prefix + directory + "/" + name: data
                    for name, data in selected_files(ROOT / directory).items()
                }
            )
    return members


def package(destination):
    # Inspect required source before creating an output directory.
    for name in PUBLIC_ROOT_FILES:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Required regular public source missing: " + name)
    wheel = wheel_members()
    source = source_members()
    proof = bundle_members(
        (ROOT / "examples/ladder64.json").read_text(encoding="utf-8")
    )
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    prefix = "certloom-" + __version__
    assets = {
        prefix + "-py3-none-any.whl": wheel,
        prefix + "-source.zip": source,
        prefix + "-ladder-proof.zip": proof,
        prefix + "-diffusion-proof.zip": bundle_members(
            (ROOT / "examples/fipy-steady400.json").read_text(encoding="utf-8")
        ),
    }
    with tempfile.TemporaryDirectory(prefix="certloom-static-") as directory:
        stage = Path(directory) / "site"
        manifest = build_site(stage)
        static = selected_files(stage)
        manifest_names = set()
        for row in manifest["files"]:
            name = safe_name(row["path"])
            if name in manifest_names or name not in static:
                raise ValueError("Invalid static source manifest.")
            manifest_names.add(name)
            data = static[name]
            if len(data) != row["bytes"] or sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Static source manifest differs: " + name)
        if set(static) != manifest_names | {"source-manifest.json"}:
            raise ValueError("Static manifest does not cover its files.")
        assets[prefix + "-browser.zip"] = static
    receipts = []
    for name, members in sorted(assets.items()):
        path = destination / name
        write_archive(path, members)
        data = path.read_bytes()
        receipts.append(
            {
                "name": name,
                "bytes": len(data),
                "sha256": sha256(data).hexdigest(),
                "members": len(members),
            }
        )
    sums = "".join(row["sha256"] + "  " + row["name"] + "\n" for row in receipts)
    with (destination / "SHA256SUMS").open(
        "x", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(sums)
    return {
        "version": __version__,
        "out": str(destination),
        "assets": receipts,
        "archive_method": "stored",
        "scope": "Hashes identify bytes, not authenticity.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", required=True, help="New output directory; existing paths refuse"
    )
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.out), indent=2))
    except (OSError, ValueError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(2, "Packaging refused: " + str(error) + "\n")
