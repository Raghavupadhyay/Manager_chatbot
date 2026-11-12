"""python -m ops_copilot — starts the API server."""
import logging

import uvicorn

from ops_copilot.config import settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("ops_copilot.api.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
