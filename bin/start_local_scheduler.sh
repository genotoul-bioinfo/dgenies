#!/usr/bin/env bash

prg_dir=$1
python=$2
pid_file=$3

cd ${prg_dir}

is_started=0

if [ -f "${pid_file}" ]; then
    pid=`cat .local_scheduler_pid`
    if ps -p"$pid" -o "pid=" > /dev/null; then
        is_started=1
    fi
fi

if [ "$is_started" -eq "0" ]; then
    echo "Starting scheduler..."
    ${python} bin/local_scheduler.py > /dev/null &
    echo $! > ${pid_file}
else
    echo "Already started!"
fi