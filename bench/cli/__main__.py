"""Entry point of the `bench` command: `python -m bench.cli <command>` (bench.cmd sets the path)."""
import sys

from bench.core import sweep

if __name__ == "__main__":
    sys.exit(sweep.main())
