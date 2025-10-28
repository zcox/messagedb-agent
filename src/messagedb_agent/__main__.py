"""Make package runnable with python -m messagedb_agent.

This module provides the entry point for running the package as a module
(python -m messagedb_agent) and for the installed console script (messagedb-agent).
"""

import sys

from messagedb_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
