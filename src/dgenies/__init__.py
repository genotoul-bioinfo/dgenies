import os
import logging
from logging.config import dictConfig
from flask import Flask
from .lib.crons import Crons
from .config_reader import AppConfigReader
# Do not display log unless a logger is defined
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

VERSION = "1.5.0"

app = None
app_title = None
APP_DATA = None
config_reader = None
mailer = None
app_folder = None
MODE = "webserver"
DEBUG = False


def set_logger(level='INFO'):
    dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
            }
        },
        'handlers': {
            'stderr': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stderr',
                'formatter': 'default'
            }
        },
        'loggers': {
            __name__: {
                'level': level,
                'handlers': ['stderr']
            },
            'werkzeug': {
                'level': level,
                'handlers': ['stderr']
            }
        }
    })


def launch(mode="webserver", config=[], tools_config=None, flask_config=None, debug=False):
    """
    Launch the application

    :param mode: webserver or standalone
    :type mode: str
    :param config: dgenies config files
    :type config: list
    :param tools_config: tools config file
    :type tools_config: str
    :param flask_config: flask config file
    :type flask_config: str
    :param debug: True to enable debug mode, override value set in flask_config
    :type debug: bool
    :return: flask app object
    :rtype: Flask
    """
    global app, app_title, app_folder, APP_DATA, config_reader, mailer, MODE, DEBUG
    app_folder = os.path.dirname(os.path.realpath(__file__))

    MODE = mode
    DEBUG = debug
    set_logger(level=logging.DEBUG if DEBUG else logging.INFO)

    # Init config reader:
    config_reader = AppConfigReader(config)
    if mode == "webserver":
        from . import database
        database.initialize()
    if tools_config:
        from .tools import Tools
        Tools(tools_config)

    UPLOAD_FOLDER = config_reader.upload_folder
    APP_DATA = config_reader.app_data

    from flask_openapi3 import OpenAPI

    app_title = "D-GENIES - Dotplot large Genomes in an Interactive, Efficient and Simple way"

    # Init Flask:
    app = OpenAPI(__name__, static_url_path='/static')
    from .api import api
    app.register_api(api)

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = config_reader.max_upload_file_size
    app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'
    if flask_config:
        logger.info("Loading flask config {}".format(flask_config))
        app.config.from_pyfile(flask_config)

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
