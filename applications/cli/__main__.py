"""Module execution adapter for ``python -m applications.cli``."""

from applications.cli import main

raise SystemExit(main())
