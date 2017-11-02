#!/bin/bash

set -e

minimap_exec=$1
nb_threads=$2
fasta_t=$3
fasta_q=$4
query=$5
target=$6
paf=$7
paf_raw=$8
out_dir=$9

# Run minimap:

if [ "$fasta_t" != "NONE" ]; then

echo "Running: ${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf_raw}

else

echo "Running: ${minimap_exec} -t ${nb_threads} -X ${fasta_q} ${fasta_q} > ${paf_raw}"

${minimap_exec} -t ${nb_threads} -X ${fasta_q} ${fasta_q} > ${paf_raw}

fi

# Sort PAF file:
sort_paf.py -i ${paf_raw} -o ${paf}

# Remove raw file:
rm -f ${paf_raw}