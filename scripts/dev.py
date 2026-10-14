import os

import uvicorn

from sonda.config import Settings


def main() -> None:
    settings = Settings.from_env(os.environ)
    uvicorn.run(
        "sonda.main:app",
        host="127.0.0.1",
        port=settings.port,
        loop="sonda.runtime:selector_loop",
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
