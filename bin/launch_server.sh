#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`

debug=0;
if [ "$1" == "debug" ]; then
    debug=1;
fi

FLASK_DEBUG=${debug} FLASK_APP=${SCRIPTPATH}/../srv/main.py flask run --host=0.0.0.0
