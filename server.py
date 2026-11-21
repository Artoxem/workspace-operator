import asyncio
import sys

from workspace_operator.config import ConfigFileError
from workspace_operator.server import run


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except ConfigFileError as exc:
        print(f"error: {exc}")
        sys.exit(2)
