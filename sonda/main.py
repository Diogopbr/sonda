import os

from sonda.config import Settings
from sonda.db import Database
from sonda.http.app import create_app

settings = Settings.from_env(os.environ)
app = create_app(settings, Database(settings))
