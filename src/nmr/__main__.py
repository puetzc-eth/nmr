"""Entry point: `python -m nmr` or the installed `nmr` command."""

import sys


def main() -> int:
    from nmr.gui.app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
