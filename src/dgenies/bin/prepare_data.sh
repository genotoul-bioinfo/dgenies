#!/usr/bin/env bash

set -e

time_file=$1
python_exec=$2
fasta_t=$3
name_t=$4
idx_t=$5
fasta_q=$6
name_q=$7
fasta_q_split=$8

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo `date +"%s"` > ${time_file}

cd ${DIR}

# Split query:
if [ -n "${fasta_q}" ] ; then
    echo "Splitting query..."
    ${python_exec} split_fa.py -i ${fasta_q} -n ${name_q} -o ${fasta_q_split}
fi

# Index target:
echo "Indexing target..."
${python_exec} build_index.py -i ${fasta_t} -n ${name_t} -o ${idx_t}

echo `date +"%s"` >> ${time_file}