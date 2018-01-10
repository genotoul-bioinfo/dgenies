#!/usr/bin/env python3

import os
from flask import Flask
from .config_reader import AppConfigReader
from .lib.mailer import Mailer
from .lib.crons import Crons

app = None
app_title = None
APP_DATA = None
config_reader = None
mailer = None


def launch():
    global app, app_title, APP_DATA, config_reader, mailer
    app_folder = os.path.dirname(os.path.realpath(__file__))


    # Init config reader:
    config_reader = AppConfigReader()

    UPLOAD_FOLDER = config_reader.upload_folder
    APP_DATA = config_reader.app_data

    app_title = "D-GENIES - Dotplot for Genomes Interactive, E-connected and Speedy"

    # Init Flask:
    app = Flask(__name__, static_url_path='/static')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = config_reader.max_upload_file_size
    app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'

    # Init mail:
    mailer = Mailer(app)

    if config_reader.debug and config_reader.log_dir != "stdout" and not os.path.exists(config_reader.log_dir):
        os.makedirs(config_reader.log_dir)

    # Crons:
    if os.getenv('DISABLE_CRONS') != "True":
        print("Starting crons...")
        crons = Crons(app_folder, config_reader.debug or os.getenv('LOGS') == "True")
        crons.start_all()

    from dgenies import views

    return app
