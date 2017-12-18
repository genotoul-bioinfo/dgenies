#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname ${SCRIPT}`

DEBUG=False
LOCAL=False
PORT=5000
DISABLE_CRONS=False

function usage()
{
    echo "Launch the server"
    echo ""
    echo "./launch_server.sh"
    echo -e "\t-h,--help\tShow this help"
    echo -e "\t--debug=${DEBUG}\tTrue to run in debug mode"
    echo -e "\t--local=${LOCAL}\tTrue to make the website accessible only on the hosting PC"
    echo -e "\t--port=${PORT}\tPort number onto run the server"
    echo -e "\t--crons=${CRONS}\tStart crons (disable it only for tests)"
    echo ""
}

function is_bool()
{
    if [ "$1" != "True" ] && [ "$1" != "False" ]; then
        echo "$2: error: $1 is not 'True' or 'False': invalid parameter"
        exit 1
    fi
}

function is_number()
{
    re='^[0-9]+$'
    if ! [[ $1 =~ $re ]] ; then
       echo "$2: error: $1 is not a number: invalid parameter"; exit 1
    fi
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
            is_bool ${VALUE} "--debug"
            DEBUG=${VALUE}
            ;;
        --local)
            is_bool ${VALUE} "--local"
            LOCAL=${VALUE}
            ;;
        --port)
            is_number ${VALUE} "--port"
            PORT=${VALUE}
            ;;
        --crons)
            is_bool ${VALUE} "--crons"
            if [[ ${VALUE} == "False" ]]; then
                DISABLE_CRONS="True"
            fi
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

DISABLE_CRONS=${DISABLE_CRONS} FLASK_DEBUG=${debug} FLASK_APP=${SCRIPTPATH}/../srv/main.py flask run --host=${host} --port=${PORT}
