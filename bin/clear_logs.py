#!/usr/bin/env python3

import os
import sys
from glob import glob

app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "srv")
sys.path.insert(0, app_folder)

from config_reader import AppConfigReader

config = AppConfigReader()

if hasattr(config, "log_dir"):
    log_files = glob(os.path.join(config.log_dir, "*.log"))
    for file in log_files:
        os.remove(file)

else:
    print("No log dir defined!")
