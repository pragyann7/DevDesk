"""CLI entry point for `python -m devdesk` and the `devdesk` script."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devdesk",
        description="Universal terminal-based development dashboard.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new .devdesk/config.toml in the current directory.")
    init_parser.add_argument("path", nargs="?", default=".", help="Directory to initialize (default: current).")

    # run command (implicit default)
    run_parser = subparsers.add_parser("run", help="Run DevDesk (default command).")
    run_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Optional path to a project containing .devdesk/config.toml",
    )

    # Handle the case where no subcommand is provided but a path is
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        args = parser.parse_args(["run"])
    elif argv[0] not in ["init", "run"]:
        # If the first arg isn't a command, assume it's a project path for the 'run' command
        args = parser.parse_args(["run", *argv])
    else:
        args = parser.parse_args(argv)

    if args.command == "init":
        from pathlib import Path
        from devdesk.utils.init_project import init_project
        try:
            path = Path(args.path).resolve()
            config_path, messages = init_project(path)
            for msg in messages:
                print(msg)
            print("Edit the config.toml file to define your project services.")
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    from devdesk.app import DevDeskApp
    DevDeskApp(initial_project=args.project).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
