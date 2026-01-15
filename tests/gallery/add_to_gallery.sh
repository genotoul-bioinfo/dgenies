#!/bin/bash

JOB_NAME="gallery" 
PICTURE="gallery.png"

../../src/bin/dgenies-api align --name "$JOB_NAME" --target ../data/ensembl_104/Escherichia_coli_o157_h7_str_sakai_gca_000008865.ASM886v2.dna.toplevel.fa.gz --query ../data/ensembl_104/Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz --email foo@example.com

export PYTHONPATH="$PYTHONPATH:$PWD/../../src"

APP_DIR="$(../../src/bin/dgenies debug | grep '^app_data:' | sed -e 's/[^:]\+: *//')"
cp "$PICTURE" "$APP_DIR/gallery/"
../../src/bin/dgenies gallery add -i "$JOB_NAME" -n "Test Gallery" -q Query -t Target -p "$PICTURE"

# try to remove job in gallery

../../src/bin/dgenies-api delete "$JOB_NAME"