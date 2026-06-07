"""Permite rodar como módulo:  python3 -m wic <descrição>"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
