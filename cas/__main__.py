"""cas command-line tool entry point.

Allows running via: python -m cas <subcommand>
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
