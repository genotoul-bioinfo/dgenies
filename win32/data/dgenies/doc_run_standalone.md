How to run a job?
-----------------

![illustrating](/static/images/D-GENIES-run-standalone.png)

### (1) Main menu

You just need to click on the *run* tab of the main menu, and follow the fields. All results will be stored in the result menu.

### (2) Updatable job name

Required field

An unique job name is set automatically. You could change it. Note that is a job already exists with this name, it will be automatically renamed.

### (3) Target file

Required field

With the selector at the left, you can choose giving a local file or an URL. For a local file, select it by clicking on the button at the right.

File must be in fasta format. We recommend using gzipped files to preserve bandwidth and faster job submission.

Allowed extensions: fa, fasta, fna, fa.gz, fasta.gz, fna.gz

Max file size: ###size### (###size_unc### once uncompressed, ###size_ava### in all-vs-all mode)

### (4) Query file

Optional field

Works like the target file. If not given, target file will be mapped to itself, in all-vs-all mode.

Max file size: ###size### (###size_unc### once uncompressed)