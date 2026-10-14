import os
import sys
from urllib.parse import urlsplit

import uvicorn

from sonda.config import Settings
from sonda.db import Database
from sonda.http.app import create_app

settings = Settings.from_env(os.environ)
url = urlsplit(settings.database_url)
if (
    settings.environment != "test"
    or url.hostname not in {"127.0.0.1", "localhost"}
    or url.path != "/sonda_test"
    or url.username != "sonda_test"
):
    raise RuntimeError("HTTP test worker requires isolated sonda_test")
app = create_app(settings, Database(settings, sys.argv[1]))
uvicorn.run(
    app,
    host="127.0.0.1",
    port=int(sys.argv[2]),
    loop="sonda.runtime:selector_loop",
    proxy_headers=False,
)
