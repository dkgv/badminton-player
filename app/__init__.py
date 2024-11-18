import os

from dotenv import load_dotenv
from flask import Flask

load_dotenv()
is_production = os.getenv("ENVIRONMENT") == "production"


def create_app() -> Flask:
    app = Flask(__name__)

    with app.app_context():
        from app.routes import api, views

        return app
