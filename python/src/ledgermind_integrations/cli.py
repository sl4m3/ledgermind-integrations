"""CLI for installing LedgerMind client integrations."""

from __future__ import annotations

import argparse

from .installer import install_hermes, uninstall_hermes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledgermind-integrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install", help="install an integration")
    install_subparsers = install.add_subparsers(dest="adapter", required=True)
    hermes = install_subparsers.add_parser("hermes")
    hermes.add_argument("--destination", help="parent directory for the plugin")
    uninstall = subparsers.add_parser("uninstall", help="remove an integration")
    uninstall_subparsers = uninstall.add_subparsers(dest="adapter", required=True)
    hermes_uninstall = uninstall_subparsers.add_parser("hermes")
    hermes_uninstall.add_argument("--destination", help="parent directory for the plugin")
    args = parser.parse_args(argv)
    if args.command == "install" and args.adapter == "hermes":
        print(install_hermes(args.destination))
        return 0
    if args.command == "uninstall" and args.adapter == "hermes":
        print(uninstall_hermes(args.destination))
        return 0
    parser.error("unsupported command")
