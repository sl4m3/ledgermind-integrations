"""CLI for installing LedgerMind client integrations."""

from __future__ import annotations

import argparse

from .installer import install_hermes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledgermind-integrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install")
    install_subparsers = install.add_subparsers(dest="adapter", required=True)
    hermes = install_subparsers.add_parser("hermes")
    hermes.add_argument("--destination")
    args = parser.parse_args(argv)
    if args.command == "install" and args.adapter == "hermes":
        print(install_hermes(args.destination))
        return 0
    parser.error("unsupported command")
