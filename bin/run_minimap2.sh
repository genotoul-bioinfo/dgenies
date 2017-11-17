#!/bin/bash

set -e

minimap_exec=$1
nb_threads=$2
fasta_t=$3
fasta_q=$4
paf=$5
paf_raw=$6

# Run minimap:

if [ "$fasta_q" != "NONE" ]; then

echo "Running: ${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}

else

echo "Running: ${minimap_exec} -t ${nb_threads} -X ${fasta_t} ${fasta_t} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} -X ${fasta_t} ${fasta_t} > ${paf_raw}

fi

# Sort PAF file:
sort_paf.py -i ${paf_raw} -o ${paf}

# Remove raw file:
rm -f ${paf_raw}