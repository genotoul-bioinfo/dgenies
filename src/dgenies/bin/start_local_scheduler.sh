#!/usr/bin/env bash

prg_dir=$1
python=$2
pid_file=$3
logs=$4

cd ${prg_dir}

is_started=0

if [ -f "${pid_file}" ]; then
    pid=`cat ${pid_file}`
    if ps -p"$pid" -o "pid=" > /dev/null; then
        is_started=1
    fi
fi

if [ "$is_started" -eq "0" ]; then
    args="-d False"
    if [ "${logs}" != "None" ]; then
        args="-d True -l ${logs}"
    fi
    echo "Starting scheduler..."
    ${python} bin/local_scheduler.py ${args} &> /dev/null &
    echo $! > ${pid_file}
else
    echo "Already started!"
fi