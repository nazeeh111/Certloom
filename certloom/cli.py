"""Command-line verification and explicit artifact export."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .artifact import read_certificate, verify_bundle, write_bundle
from .publication import fresh_output
from .engine import VerificationError, verify_text
from .site import build


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="certloom",
        description="Numerical answers with independently checkable error bounds.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify", help="Recompute an exact stored-system certificate"
    )
    verify.add_argument("certificate")
    verify.add_argument(
        "--out", help="Write a separate JSON result; existing files refuse"
    )
    bundle = commands.add_parser(
        "bundle", help="Export input, result and standalone Python checker"
    )
    bundle.add_argument("certificate")
    bundle.add_argument("--out", required=True)
    bundle_verify = commands.add_parser("verify-bundle", help="Check a bundle using the installed trusted engine")
    bundle_verify.add_argument("bundle")
    site = commands.add_parser(
        "build-site", help="Build a static browser lab into a new directory"
    )
    site.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build-site":
            result = build(args.out)
            print(json.dumps({"out": args.out, "files": len(result["files"])}))
        elif args.command == "bundle":
            print(
                json.dumps(write_bundle(read_certificate(args.certificate), args.out))
            )
        else:
            result = verify_bundle(args.bundle) if args.command == "verify-bundle" else verify_text(read_certificate(args.certificate))
            text = json.dumps(result, indent=2) + "\n"
            if getattr(args, "out", None):
                with fresh_output(args.out) as stream:
                    stream.write(text.encode("utf-8"))
            else:
                sys.stdout.write(text)
            verdict = result["result"] if args.command == "verify-bundle" else result
            if verdict["status"] != "certified":
                return 3
    except (VerificationError, OSError, UnicodeError) as error:
        print("Verification refused: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
