#!/usr/bin/env bash

if [ ! $(which index.js) ] ; then
    echo """
    ERROR: minifier is not installed!

    Install it through npm:
    npm install --prefix ~ minifier

    Then, add it to the PATH:
    export PATH=\$PATH:~/node_modules/minifier
    """
    exit 1
fi

cd src/dgenies/static/css

index.js -o dgenies.min.css dgenies.css
