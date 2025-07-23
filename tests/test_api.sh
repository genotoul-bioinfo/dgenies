#!/bin/bash

ENDPOINT="http://127.0.0.1:5000/api/v1"
QUERY="./data/ensembl_104/Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz"
TARGET="./data/ensembl_104/Escherichia_coli_o157_h7_str_sakai_gca_000008865.ASM886v2.dna.toplevel.fa.gz"
JOB_NAME="api"
EMAIL="name@example.com"

QUERY_NAME="$(basename ${QUERY})"
TARGET_NAME="$(basename ${TARGET})"


echo "Submit align job"
echo
msg="$(curl -X 'POST' \
  "${ENDPOINT}/job" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'email='"${EMAIL}"'' \
  -F 'batch_id='"${JOB_NAME}"'' \
  -F 'jobs={
  "backup": "",
  "align": "",
  "query": "'"${QUERY_NAME}"'",
  "target_type": "local",
  "query_type": "local",
  "target": "'"${TARGET_NAME}"'",
  "align_type": "local",
  "backup_type": "local",
  "tool": "minimap2",
  "job_id": "'"${JOB_NAME}"'",
  "type": "align",
  "tool_option": ["repeat:few"]
}' \
  -F 'nb_jobs=1')"

echo "$msg"

session_id="$(echo "$msg" | jq -r ".data.session_id" )"
echo
echo "Will use session id: ${session_id}"

sleep 1

echo
echo "Upload query file: ${QUERY}"
echo
msg="$(curl -X 'POST' \
  "${ENDPOINT}/upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@'"${QUERY}"';type=application/gzip' \
  -F "session_id=${session_id}")"

echo "$msg"

#echo
#query_name="$(echo "${msg}" | jq -r ".data.file.name" )"
#echo "${query_name}"

sleep 1

echo
echo "Upload query file again: ${QUERY}"
echo
curl -X 'POST' \
  "${ENDPOINT}/upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@'"${QUERY}"';type=application/gzip' \
  -F "session_id=${session_id}"


sleep 1

echo
echo "Upload target file: ${TARGET}"
echo
msg="$(curl -X 'POST' \
  "${ENDPOINT}/upload" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@'"${TARGET}"';type=application/gzip' \
  -F "session_id=${session_id}")"

echo "$msg"
#echo
#target_name="$(echo "${msg}" | jq -r ".data.file.name" )"
batch_id="$(echo "${msg}" | jq -r ".data.batch_id" )"
#echo "${target_name}"

echo "Running with id: ${batch_id}"

sleep 1

echo
echo "Get status"
echo
curl -X 'GET' \
  "${ENDPOINT}/status/${batch_id}" \
  -H 'accept: application/json'

sleep 1

echo
echo "Get status"
echo
curl -X 'GET' \
  "${ENDPOINT}/status/${batch_id}" \
  -H 'accept: application/json'



sleep 10

echo
echo "Get dotplot"
echo
curl -X 'GET' \
  "${ENDPOINT}/result/${batch_id}/dotplot" \
  -H 'accept: application/json'
