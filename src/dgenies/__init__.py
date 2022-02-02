#!/usr/bin/env python3

import os
from flask import Flask
from .config_reader import AppConfigReader
from .lib.crons import Crons

VERSION = "1.3.0"

app = None
app_title = None
APP_DATA = None
config_reader = None
mailer = None
app_folder = None
MODE = "webserver"
DEBUG = False


def launch(mode="webserver", debug=False):
    """
    Launch the application

    :param mode: webserver or standalone
    :type mode: str
    :param debug: True to enable debug mode
    :type debug: bool
    :return: flask app object
    :rtype: Flask
    """
    global app, app_title, app_folder, APP_DATA, config_reader, mailer, MODE, DEBUG
    app_folder = os.path.dirname(os.path.realpath(__file__))

    MODE = mode
    DEBUG = debug

    # Init config reader:
    config_reader = AppConfigReader()

    UPLOAD_FOLDER = config_reader.upload_folder
    APP_DATA = config_reader.app_data

    app_title = "D-GENIES - Dotplot large Genomes in an Interactive, Efficient and Simple way"

    # Init Flask:
    app = Flask(__name__, static_url_path='/static')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = config_reader.max_upload_file_size
    app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'

    # Init mail:
    if MODE == "webserver":
        from .lib.mailer import Mailer
        mailer = Mailer(app)

    # Create data dir if not exists
    if not os.path.exists(config_reader.app_data):
        os.makedirs(config_reader.app_data)

    if config_reader.debug and config_reader.log_dir != "stdout" and not os.path.exists(config_reader.log_dir):
        os.makedirs(config_reader.log_dir)

    # Crons:
    if os.getenv('DISABLE_CRONS') != "True" and MODE == "webserver":
        print("Starting crons...")
        crons = Crons(app_folder, config_reader.debug or os.getenv('LOGS') == "True")
        crons.start_all()

    from dgenies import views

    return app
