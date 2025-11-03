#!/bin/bash

../src/bin/dgenies-api align \
  --target ./data/ensembl_104/Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz \
  --tool minimap2 \
  --options repeat:few