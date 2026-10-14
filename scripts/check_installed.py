"""Check an offline wheel install from a fresh virtual environment.

Use --wheel to create and check a fresh offline install, or run this script
with an already freshly installed environment's Python. Source imports refuse.
"""

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path, PurePosixPath

SKIP = {
    "__pycache__",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def selected(directory):
    files = {}
    for source in sorted(directory.rglob("*")):
        relative = source.relative_to(directory)
        if any(part in SKIP or part.startswith("._") for part in relative.parts):
            continue
        if source.name == ".DS_Store" or source.suffix in (".pyc", ".pyo"):
            continue
        if source.is_symlink():
            raise AssertionError("Symlink resource refused: " + str(source))
        if source.is_file():
            files[relative.as_posix()] = source.read_bytes()
    return files


def safe_archive(archive):
    seen = set()
    assert archive.testzip() is None, "ZIP CRC check failed"
    for member in archive.infolist():
        name = member.filename
        path = PurePosixPath(name)
        assert name and not path.is_absolute() and str(path) == name
        assert "\\" not in name and all(part not in (".", "..") for part in path.parts)
        assert all(ord(char) >= 32 for char in name)
        assert name.casefold() not in seen, "Duplicate ZIP member"
        seen.add(name.casefold())
        mode = member.external_attr >> 16
        assert not member.is_dir() and (stat.S_IFMT(mode) in (0, stat.S_IFREG)), (
            "Non-regular ZIP member"
        )


def check(source):
    assert sys.prefix != sys.base_prefix, (
        "Run with Python from the fresh installed virtual environment"
    )
    import certloom
    from certloom.artifact import bundle_members
    from certloom.engine import verify_text

    source = source.resolve()
    package = Path(certloom.__file__).resolve().parent
    try:
        package.relative_to(Path(sys.prefix).resolve())
    except ValueError as error:
        raise AssertionError(
            "Source import instead of installed package: " + str(package)
        ) from error
    expected = selected(source / "certloom")
    for directory in ("web", "examples", "docs"):
        expected.update(
            {
                directory + "/" + name: data
                for name, data in selected(source / directory).items()
            }
        )
    expected["licenses/LICENSE"] = (source / "LICENSE").read_bytes()
    installed = selected(package)
    assert set(installed) == set(expected), (
        "Installed resource paths differ from selected source"
    )
    for name, data in expected.items():
        assert installed[name] == data, "Installed resource bytes differ: " + name
    installed_distribution = distribution("certloom")
    license_files = installed_distribution.metadata.get_all("License-File", [])
    assert license_files, "Installed license metadata is missing"
    metadata_entries = [
        file
        for file in installed_distribution.files
        if str(file).endswith(".dist-info/METADATA")
    ]
    assert len(metadata_entries) == 1, "Installed metadata file is ambiguous"
    metadata_directory = Path(
        installed_distribution.locate_file(metadata_entries[0])
    ).parent
    for name in license_files:
        relative = PurePosixPath(name)
        assert (
            not relative.is_absolute()
            and ".." not in relative.parts
            and "\\" not in name
        )
        assert (metadata_directory / "licenses" / name).read_bytes() == expected[
            "licenses/LICENSE"
        ], "License metadata does not resolve to the MIT license bytes"

    executable = Path(sys.prefix) / (
        "Scripts/certloom.exe" if os.name == "nt" else "bin/certloom"
    )
    assert executable.is_file(), "Installed console script is missing"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    checks = [
        "fresh virtual environment imports installed package",
        "installed package paths and bytes match source",
        "PEP639 License-File metadata resolves to complete MIT license bytes",
    ]

    with tempfile.TemporaryDirectory(prefix="certloom-installed-") as directory:
        temporary = Path(directory)

        def run(arguments, code=0):
            completed = subprocess.run(
                [str(value) for value in arguments],
                cwd=temporary,
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            assert completed.returncode == code, (
                "Command exit differed: "
                + repr([str(value) for value in arguments])
                + "\nstdout: "
                + completed.stdout[:1000]
                + "\nstderr: "
                + completed.stderr[:1000]
            )
            return completed

        help_result = run([executable, "--help"])
        assert (
            "verify" in help_result.stdout
            and "build-site" in help_result.stdout
            and "bundle" in help_result.stdout
        )
        assert run([executable, "--version"]).stdout.strip() == certloom.__version__
        checks.append("installed console help, commands and version")

        ladder = package / "examples/ladder64.json"
        hilbert12 = package / "examples/hilbert12.json"
        ladder_text = ladder.read_text(encoding="utf-8")
        expected_ladder = verify_text(ladder_text)
        assert (
            expected_ladder["status"] == "certified"
            and expected_ladder["dimension"] == 64
        )
        assert expected_ladder["decision"]["status"] == "above"
        assert json.loads(run([executable, "verify", ladder]).stdout) == expected_ladder
        refusal = json.loads(run([executable, "verify", hilbert12], 3).stdout)
        assert refusal["status"] == "not_certified"
        assert (
            "radius" not in refusal
            and "enclosures" not in refusal
            and "decision" not in refusal
        )
        checks.append("actual installed ladder claim and Hilbert12 refused exit3")

        result_path = temporary / "result.json"
        run([executable, "verify", ladder, "--out", result_path])
        before = result_path.read_bytes()
        run([executable, "verify", hilbert12, "--out", result_path], 2)
        assert result_path.read_bytes() == before
        checks.append("existing verification output refused without changing bytes")

        site = temporary / "site"
        run([executable, "build-site", "--out", site])
        manifest = json.loads(
            (site / "source-manifest.json").read_text(encoding="utf-8")
        )
        files = selected(site)
        seen = set()
        for row in manifest["files"]:
            name = row["path"]
            assert name not in seen and name in files
            seen.add(name)
            data = files[name]
            assert (
                len(data) == row["bytes"] and sha256(data).hexdigest() == row["sha256"]
            )
        assert set(files) == seen | {"source-manifest.json"}
        for resource in ("web", "examples", "docs"):
            for name, data in selected(package / resource).items():
                if resource == "docs" and Path(name).suffix not in (".html", ".css"):
                    continue
                target_name = name if resource == "web" else resource + "/" + name
                assert files[target_name] == data
        assert files["LICENSE.txt"] == expected["licenses/LICENSE"]
        site_before = {name: sha256(data).hexdigest() for name, data in files.items()}
        run([executable, "build-site", "--out", site], 2)
        assert {
            name: sha256(data).hexdigest() for name, data in selected(site).items()
        } == site_before
        checks.append(
            "installed static site resources, complete manifest and no-clobber"
        )

        bundle = temporary / "ladder.zip"
        run([executable, "bundle", ladder, "--out", bundle])
        original_bundle = bundle.read_bytes()
        run([executable, "bundle", ladder, "--out", bundle], 2)
        assert bundle.read_bytes() == original_bundle
        reference_members = bundle_members(ladder_text)
        detached = temporary / "detached"
        detached.mkdir()
        with zipfile.ZipFile(bundle) as archive:
            safe_archive(archive)
            assert set(archive.namelist()) == set(reference_members)
            for name, data in reference_members.items():
                assert archive.read(name) == data
                with (detached / name).open("xb") as stream:
                    stream.write(data)
        assert (detached / "certificate.json").read_bytes() == ladder.read_bytes()
        detached_result = json.loads(
            run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    detached / "checker.py",
                    detached / "certificate.json",
                ]
            ).stdout
        )
        receipt = json.loads(
            (detached / "verification.json").read_text(encoding="utf-8")
        )
        assert detached_result == expected_ladder == receipt["result"]
        assert receipt["certificate_sha256"] == sha256(ladder.read_bytes()).hexdigest()
        for line in (detached / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            assert sha256((detached / name).read_bytes()).hexdigest() == digest
        checks.append("portable bundle paths, CRCs, source bytes, receipt and hashes")
        checks.append(
            "detached checker with -I -S exactly agrees with installed verifier"
        )
        refusal_path = detached / "refusal.json"
        refusal_path.write_bytes(hilbert12.read_bytes())
        assert (
            json.loads(
                run(
                    [sys.executable, "-I", "-S", detached / "checker.py", refusal_path],
                    3,
                ).stdout
            )
            == refusal
        )
        checks.append("detached checker preserves failed-premise exit3")

    return {
        "version": certloom.__version__,
        "python": sys.version.split()[0],
        "installed": str(package),
        "source_equal_files": len(expected),
        "static_manifest_files": len(seen),
        "checks": checks,
        "scope": "Actual local installed-resource and detached checker validation; not physical-model or source-authenticity verification.",
    }


def bootstrap(wheel, source, receipt):
    wheel = wheel.resolve()
    assert wheel.is_file() and wheel.suffix == ".whl", "A local wheel is required"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="certloom-fresh-install-") as directory:
        virtual = Path(directory) / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(virtual)],
            env=environment,
            check=True,
            timeout=120,
        )
        python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--no-cache-dir",
                "--disable-pip-version-check",
                str(wheel),
            ],
            env=environment,
            check=True,
            timeout=120,
            stdout=sys.stderr,
        )
        arguments = [
            str(python),
            str(Path(__file__).resolve()),
            "--source",
            str(source.resolve()),
        ]
        if receipt is not None:
            arguments.extend(["--out", str(receipt.resolve())])
        completed = subprocess.run(
            arguments,
            env=environment,
            check=True,
            timeout=120,
            text=True,
            capture_output=True,
        )
        return completed.stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help="Create a fresh virtual environment and install this local wheel offline",
    )
    parser.add_argument(
        "--out", type=Path, help="Optional new receipt path; existing files refuse"
    )
    args = parser.parse_args()
    if args.wheel:
        print(bootstrap(args.wheel, args.source, args.out), end="")
        raise SystemExit(0)
    result = check(args.source)
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")
