#!/bin/bash

../src/bin/dgenies-api align \
  --target "https://ftp.ensemblgenomes.ebi.ac.uk/pub/bacteria/release-62/fasta/bacteria_0_collection/escherichia_coli_str_k_12_substr_mg1655_gca_000005845/dna/Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz" \
  --query "http://ftp.ensemblgenomes.org/pub/bacteria/release-62/fasta/bacteria_79_collection/escherichia_coli_str_k_12_substr_w3110_gca_000010245/dna/Escherichia_coli_str_k_12_substr_w3110_gca_000010245.ASM1024v1_.dna.toplevel.fa.gz" \
  --tool minimap2 \
  --options repeat:few