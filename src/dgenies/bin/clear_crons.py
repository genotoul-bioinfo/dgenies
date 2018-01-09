#!/usr/bin/env python3

import os
from dgenies.lib.crons import Crons

app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "dgenies")

crons = Crons(app_folder)
crons.clear()
