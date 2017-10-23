#!/bin/bash

set -e

minimap_exec=$1
samtools_exec=$2
nb_threads=$3
fasta_t=$4
fasta_q=$5
query=$6
target=$7
paf=$8
out_dir=$9

# Index fasta files:
${samtools_exec} faidx ${fasta_q}

# Run minimap:

if [ "$fasta_t" != "NONE" ]; then

${samtools_exec} faidx ${fasta_t}

${minimap_exec} -t ${nb_threads} ${fasta_t} ${fasta_q} > ${paf}

# Parse paf raw file:
build_indexes.py -q ${fasta_q} -t ${fasta_t} -o ${out_dir} -r ${query} -u ${target}

else

echo "Running: ${minimap_exec} -t ${nb_threads} -X ${fasta_q} ${fasta_q} > ${paf}"

${minimap_exec} -t ${nb_threads} -X ${fasta_q} ${fasta_q} > ${paf}

# Parse paf raw file:
build_indexes.py -q ${fasta_q} -t ${fasta_q} -o ${out_dir} -r ${query} -u ${query}

fi