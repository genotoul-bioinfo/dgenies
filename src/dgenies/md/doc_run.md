How to run a job?
-----------------

### New alignment mode

Launch a new mapping between two fasta files and dot plot it.

{% if mode == "webserver" %}
![illustrating](/static/images/D-GENIES-run_na.png)
{% else %}
![illustrating](/static/images/D-GENIES-run-standalone_na.png)
{% endif %}

{% set puce=1 %}

#### ({{puce}}) Main menu

You just need to click on the *run* tab of the main menu, and follow the fields. All results will be stored in the result menu.

{% set puce=puce+1 %}

#### ({{puce}}) Updatable job name

Required field

An unique job name is set automatically. You could change it. Note that is a job already exists with this name, it will be automatically renamed.

{% set puce=puce+1 %}

{% if mode == "webserver" %}

#### ({{puce}}) User email

Required field

Please fill your email. When the mail will be finished, you will receive a mail to inform you that your job is done. Also, some features in the result page will send you a mail to this address.

{% set puce=puce+1 %}

{% endif %}

#### ({{puce}}) Target fasta

Required field

With the selector at the left, you can choose giving a local file or an URL. For a local file, select it by clicking on the button at the right.

File must be in fasta format. We recommend using gzipped files to preserve bandwidth and faster job submission.

Allowed extensions: fa, fasta, fna, fa.gz, fasta.gz, fna.gz

Max file size: ###size### (###size_unc### once uncompressed, ###size_ava### in all-vs-all mode)

{% set puce=puce+1 %}

#### ({{puce}}) Query fasta

Optional field

Works like the target fasta. If not given, target file will be mapped to itself, in all-vs-all mode.

Max file size: ###size### (###size_unc### once uncompressed)

{% set puce=puce+1 %}

### Plot alignment mode

Dot plot an existing alignment file.

{% if mode == "webserver" %}
![illustrating](/static/images/D-GENIES-run_pa.png)
{% else %}
![illustrating](/static/images/D-GENIES-run-standalone_pa.png)
{% endif %}

{% if mode == "webserver" %}
{% set puce=4 %}
{% else %}
{% set puce=3 %}
{% endif %}

For numbers from 1 to {% if mode == "webserver" %}3{% else %}2{% endif %}, see previous section.

#### ({{puce}}) Alignment file

Required field (except if backup file is filled, see bellow)

An alignment file in PAF or MAF format.

Allowed extensions: paf, maf

With the selector at the left, you can choose giving a local file or an URL. For a local file, select it by clicking on the button at the right.

{% set puce=puce+1 %}

#### ({{puce}}) Target file

Required field (except if backup file is filled, see bellow)

Could be the fasta file for the target or the corresponding index file.

To improve bandwidth and computation time, we recommend to use the index file. This file format is described [here](/documentation/formats#index-file). You can use [our tool](https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v{{version}}/src/dgenies/bin/index.py) to build it.

Allowed extensions:  
Fasta: fa, fasta, fna, fa.gz, fasta.gz, fna.gz  
Index: idx

With the selector at the left, you can choose giving a local file or an URL. For a local file, select it by clicking on the button at the right.

{% set puce=puce+1 %}

#### ({{puce}}) Query file

Optional field

Could be the fasta file for the query or the corresponding index file.

Works like the target file.

{% set puce=puce+1 %}

#### ({{puce}}) Backup file

Optional field

If you download backup from a previous job, you can add it here to restore the job. In this case, don't fill previous fields, only this one is required.

With the selector at the left, you can choose giving a local file or an URL. For a local file, select it by clicking on the button at the right.