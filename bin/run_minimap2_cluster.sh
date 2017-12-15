#!/bin/bash

set -e

minimap_exec=$1
nb_threads=$2
fasta_t=$3
fasta_q=$4
paf_raw=$5

# Run minimap:

if [ "$fasta_q" != "NONE" ]; then

echo "Running: ${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}

else

echo "Running: ${minimap_exec} -t ${nb_threads} -X ${fasta_t} ${fasta_t} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} -X ${fasta_t} ${fasta_t} > ${paf_raw}

fi
