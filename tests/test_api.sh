#!/bin/bash

ENDPOINT="http://127.0.0.1:5000/api/v1"
QUERY="./data/ensembl_104/Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz"
TARGET="./data/ensembl_104/Escherichia_coli_o157_h7_str_sakai_gca_000008865.ASM886v2.dna.toplevel.fa.gz"
JOB_NAME="api"
EMAIL="name@example.com"


# Get proposed job name

echo "Get config from ${ENDPOINT}:"
JOB_NAME="$(curl -X 'GET' \
  "${ENDPOINT}/config" \
  -H 'accept: application/json' \
  | jq -r ".data.batch_id")"

echo "Will use job id: ${JOB_NAME}"

# Get Session

echo "Get session:"
session_id="$(curl -X 'GET' \
  "${ENDPOINT}/session" \
  -H 'accept: application/json' \
  | jq -r ".data.session_id")"

echo "Will use session id: ${session_id}"

sleep 1

echo "Ask upload permission:"
curl -X 'POST' \
  "${ENDPOINT}/ask-upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F "session_id=${session_id}"

sleep 1

echo "Upload query file: ${QUERY}"
query_name="$(curl -X 'POST' \
  "${ENDPOINT}/upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@'"${QUERY}"';type=application/gzip' \
  -F 'file_roles=query' \
  -F 'job_types=align' \
  -F "session_id=${session_id}" \
  | jq -r ".data.files[0].name" )"


sleep 1

echo "Upload target file: ${TARGET}"
target_name="$(curl -X 'POST' \
  "${ENDPOINT}/upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@'"${TARGET}"';type=application/gzip' \
  -F 'file_roles=target' \
  -F 'job_types=align' \
  -F "session_id=${session_id}"\
  | jq -r ".data.files[0].name" )"

# Run job

sleep 1

echo "Submit align job"
curl -X 'POST' \
  "${ENDPOINT}/job" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'email='"${EMAIL}"'' \
  -F 'batch_id='"${JOB_NAME}"'' \
  -F 'jobs={
  "backup": "",
  "align": "",
  "query": "'"${query_name}"'",
  "target_type": "local",
  "query_type": "local",
  "target": "'"${target_name}"'",
  "align_type": "local",
  "backup_type": "local",
  "tool": "minimap2",
  "job_id": "'"${JOB_NAME}"'",
  "type": "align",
  "tool_option": ["repeat:few"]
}' \
  -F 'nb_jobs=1' \
  -F "session_id=${session_id}"
