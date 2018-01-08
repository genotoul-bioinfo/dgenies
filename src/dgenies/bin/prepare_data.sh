#!/usr/bin/env bash

set -e

python_exec=$1
fasta_t=$2
name_t=$3
idx_t=$4
fasta_q=$5
name_q=$6
fasta_q_split=$7

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd ${DIR}

# Split query:
if [ -n "${fasta_q}" ] ; then
    echo "Splitting query..."
    ${python_exec} split_fa.py -i ${fasta_q} -n ${name_q} -o ${fasta_q_split}
fi

# Index target:
echo "Indexing target..."
${python_exec} build_index.py -i ${fasta_t} -n ${name_t} -o ${idx_t}