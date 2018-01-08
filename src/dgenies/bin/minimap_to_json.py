#!/usr/bin/env python3

import os
import argparse
import tempfile
from lib.parse_paf import *
import prepare_paf

parser = argparse.ArgumentParser(description="Convert paf file to json file readable by algeco tool")
parser.add_argument('-i', '--input', type=str, required=True, help="Paf file to parse")
parser.add_argument('-q', '--query', type=str, required=True, help="Query fasta file")
parser.add_argument('-t', '--target', type=str, required=True, help="Target fasta file")
parser.add_argument('-o', '--output', type=str, required=True, help="Output json file")

args = parser.parse_args()

tmp_dir = tempfile.mkdtemp()
paf_out = os.path.join(tmp_dir, "map.paf")

# Prepare paf file
prepare_paf.init(args.input, paf_out, args.query, args.target)

# Build json
idx1 = os.path.join(tmp_dir, "query.idx")
idx2 = os.path.join(tmp_dir, "target.idx")
save_json(paf_out, idx1, idx2, args.output)
