#!/usr/bin/env bash

if [ ! $(which index.js) ] ; then
    echo """
    ERROR: minifier is not installed!

    Install it through npm:
    npm install --prefix ~ minifier

    Then, add it to the PATH:
    bash: export PATH=\$PATH:~/node_modules/minifier
    fish: set PATH \$PATH ~/node_modules/minifier
    """
    exit 1
fi

cd src/dgenies/static/css

index.js -o dgenies.min.css dgenies.css
index.js -o dgenies-offline-result.min.css chosen.min.css animate.css jquery-ui.min.css bootstrap.min.css bootstrap-theme.min.css dgenies.min.css
