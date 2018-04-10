#!/usr/bin/env python3

import argparse
import wget
import os

VERSION = "1.0.1"

parser = argparse.ArgumentParser(description="Split huge contigs")
parser.add_argument('-d', '--dir', type=str, required=False, help="Folder into store files", default=".")

args = parser.parse_args()

for file_dl in [
    "https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v%s/src/dgenies/bin/all_prepare.py" % VERSION,
    "https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v%s/src/dgenies/bin/filter_contigs.py" % VERSION,
    "https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v%s/src/dgenies/bin/index.py" % VERSION,
    "https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v%s/src/dgenies/binsplit_fa.py" % VERSION
        ]:
    d_file = os.path.join(args.dir, file_dl.rsplit("/", 1)[1])
    print("Downloading %s..." % d_file)
    wget.download(file_dl, args.dir, None)
    os.chmod(d_file, 0o755)
