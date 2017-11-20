#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname ${SCRIPT}`

DEBUG=False
LOCAL=False
PORT=5000

function usage()
{
    echo "Launch the server"
    echo ""
    echo "./launch_server.sh"
    echo -e "\t-h,--help\tShow this help"
    echo -e "\t--debug=${DEBUG}\tTrue to run in debug mode"
    echo -e "\t--local=${LOCAL}\tTrue to make the website accessible only on the hosting PC"
    echo -e "\t--port=${PORT}\tPort number onto run the server"
    echo ""
}

while [ "$1" != "" ]; do
    PARAM=`echo $1 | awk -F= '{print $1}'`
    VALUE=`echo $1 | awk -F= '{print $2}'`
    case ${PARAM} in
        -h | --help)
            usage
            exit
            ;;
        --debug)
            DEBUG=${VALUE}
            ;;
        --local)
            LOCAL=${VALUE}
            ;;
        --port)
            PORT=${VALUE}
            ;;
        *)
            echo "ERROR: unknown parameter \"${PARAM}\""
            usage
            exit 1
            ;;
    esac
    shift
done

debug=0;
if [ "$DEBUG" == "True" ]; then
    echo "Running in debug mode..."
    debug=1;
fi

host="0.0.0.0"
if [ "$LOCAL" == "True" ]; then
    host="127.0.0.1"
fi

FLASK_DEBUG=${debug} FLASK_APP=${SCRIPTPATH}/../srv/main.py flask run --host=${host} --port=${PORT}
