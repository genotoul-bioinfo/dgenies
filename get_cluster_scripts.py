#!/usr/bin/env python3

import argparse
import wget
import os

parser = argparse.ArgumentParser(description="Split huge contigs")
parser.add_argument('-d', '--dir', type=str, required=False, help="Folder into store files", default=".")

args = parser.parse_args()

for file_dl in ["https://forgemia.inra.fr/genotoul-bioinfo/dgenies/raw/master/src/dgenies/bin/all_prepare.py",
                "https://forgemia.inra.fr/genotoul-bioinfo/dgenies/raw/master/src/dgenies/bin/filter_contigs.py",
                "https://forgemia.inra.fr/genotoul-bioinfo/dgenies/raw/master/src/dgenies/bin/index.py",
                "https://forgemia.inra.fr/genotoul-bioinfo/dgenies/raw/master/src/dgenies/bin/split_fa.py"]:
    d_file = os.path.join(args.dir, file_dl.rsplit("/", 1)[1])
    print("Downloading %s..." % d_file)
    wget.download(file_dl, args.dir, None)
    os.chmod(d_file, 0o755)
