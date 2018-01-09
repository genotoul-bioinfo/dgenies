#!/usr/bin/env python3

import os
import sys
from glob import glob

from dgenies.config_reader import AppConfigReader

config = AppConfigReader()

if hasattr(config, "log_dir"):
    log_files = glob(os.path.join(config.log_dir, "*.log"))
    for file in log_files:
        os.remove(file)

else:
    print("No log dir defined!")
