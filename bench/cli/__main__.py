"""Entry point of the `bench` command: `python -m bench.cli <command>` (bench.cmd sets the path)."""
import sys

from bench.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
