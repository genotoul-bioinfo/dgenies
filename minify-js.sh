#!/usr/bin/env bash

set -e

if [ ! $(which babel.js) ] ; then
    echo """
    ERROR: babel is not installed!

    Install it through npm:
    npm install --save-dev babel-cli

    Then, add it to the PATH:
    export PATH=\$PATH:~/node_modules/babel-cli/bin
    """
    exit 1
fi

cd src/dgenies/static/js

babel.js -o dgenies.min.js --compact --minified dgenies.js dgenies.prototypes.js
babel.js -o dgenies.result.min.js --compact --minified dgenies.result.js dgenies.result.controls.js dgenies.result.export.js dgenies.result.summary.js d3.boxplot.js d3.boxplot.events.js d3.boxplot.mousetip.js d3.boxplot.zoom.js
babel.js -o jquery.fileupload.min.js --compact --minified jquery.fileupload.js jquery.fileupload-process.js jquery.fileupload-validate.js
babel.js -o dgenies.run.min.js --compact --minified dgenies.run.js
babel.js -o dgenies.status.min.js --compact --minified dgenies.status.js