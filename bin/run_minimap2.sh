#!/bin/bash

minimap_exec=$1
samtools_exec=$2
nb_threads=$3
fasta_t=$4
fasta_q=$5

${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q}
${samtools_exec} faidx ${fasta_t}
${samtools_exec} faidx ${fasta_q}
