# Changelog

## 1.5.0 (2023-0x-xx)

### Major change

If you run dgenies in webserver mode, database schema has changed.

The column `batch_type` was changed to `runner_type` in `job` table. 
You can update the database with following sql command:
  ```
  ALTER TABLE job RENAME COLUMN batch_type TO runner_type;
  ```
This change was also reflected for cluster configuration in `application.properties`, where `batch_system_type` was renamed to `runner_type`.

For users:
- Update batch mode:
	- Local files upload
	- Batch content checked in web interface
  - Single upload per file
  - Batch file format has changed, in particular, option keys have been change to be more comprehensible. Please read the doc.
- Job logs are now available to download and are included in backup file.
- Update user interface to `bootstrap 4.6`

For sysadmin
- Tools config file format (`tools.yaml`) has changed. Please update it if you use a custom one.
- Basic app logging.
- Configuration files:
  - In `application.properties`, `batch_system_type` was renamed to `runner_type` in order to avoid confusion with batch jobs intoduced with dgenies 1.4.
  - In database, the column `batch_type` was changed to `runner_type` in `job` table. 
  - It is possible to set config files directly when running dgenies with `--config` and `--tools-config` options. Please be careful to use the correct config files when managing a running instance of dgenies.
  - It is now possible to use a the option `--flask-config` in order to set some flask options. You can use it to set some email server parameters.

### Minor changes

- Dotplot:
  - You can reset the sort (usefull when plying with manual contig reversal)
  - 'Query as reference' download is now compressed in webserver mode.
- For sysadmin:
  - For server mode, the number of download sessions in parallel, can be now set with `max_download_sessions` (default is alway `5`). Session delays can also be modified now.
  - Reinforce tar file checking
  - Drop Flask<2

### Bugfix

- When sorted, "Association table", "Query Fasta" and "Query assembled as reference" files match dotplot. Before, only the last reversed contig on dotplot was token in account.
- Fix some bugs with Flask>=2
	- Add compatibility with Flask 2.2
	- Some gzipped files were uncompressed by browser when downloaded.
	- Backup file name was incomplete.

## 1.4.0 (2022-07-12)

### Major change

- Add batch mode. This early version only allows to use urls as file inputs. #28

### Minor changes

- Add definition page to explain how some things like *Identity*, *Best matching chromosomes* are computed.
- Relax Jinja and Flask requirements up to last versions

### Bugfix

- Some options were display to right side of page

## 1.3.1 (2022-03-30)

### Minor change

- Add some anonymization strategies

### Bugfix

- Fix some Jinja2 requirement constraints
- Fix exported query fasta file that was not compressed when asked.

## 1.3.0 (2022-03-01)

### Major changes

- Add `repeatedness` option with minimap2. This option needs to upgrade the database schema with following command:
  ```sql
  ALTER TABLE job ADD COLUMN options VARCHAR(127) NULL;
  ```
- Backup archive is now a `tar.gz` file. Old `tar` backup archive are still supported
- Upgrade embedded minimap2 to the latest available version (2.24)
- GDPR compliant (webserver mode):
  - Cookie wall option
  - Ability to set legal stuff pages
  - Analytics is now anonymous, an option allows to restore the previous behavior

### Other changes

- Python 3.10 compatibility
- Add a command to clean analytics DB from dgenies (`dgenies clear -a [--max-age <age>]`)
- Check if PAF file is correctly formatted
- Performance improvement
- Expose `max_nb_lines` parameter in configuration file.
- Tools can have a label now (in `tools.yaml`).
- Speedup compressed file operations by using [`xopen` library](https://github.com/pycompression/xopen)
- Fix upload form. Form is now correctly reset when a field is missing or erroneous.
- Fix filename collision. Uploading a query file and a target file with the same filename now works correctly
- Fix wrong RAM usage displayed in gallery
- Correct default `slurm` parameters to match last version of [slurm-drmaa](https://github.com/natefoo/slurm-drmaa) (1.1.3)
- Remove local scheduler pid file when stopping it
- Update documentation:
  - Explain how similarity/identity measure is computed
  - Add link in D-Genies to what is expected in backup archive
- Wiki
  - Cookbooks
  - Additional information for developers

## 1.2.0.2 (2021-11-15) - pypi release only

### Bugfixes

- Update python requirements

## 1.2.0.1 (2018-09-25) - pypi release only

Bugfix release

## 1.2.0 (2018-07-17)

### Major changes

- Dot plot have now a mouse cursor centered zoom
- Now includes [mashmap](https://github.com/marbl/MashMap) (v2.0), a faster aligner for high identity genomes, as an alternative to minimap2 (Linux only)
- Download a HTML page which permit to show an interactive dot plot offline (with the summary)
- Display match coordinates by moving the mouse cursor over the match line

### Other changes

- Upgrade embedded minimap2 to the latest available version (2.11)
- Add help messages on the interface
- Add the ability to add a message to the run form through command line (designed for maintenance for example)
- Several bug fixes


## 1.1.1 (2018-06-20)

### Bugfixes

- Fix bug with parse of MAF files
- Fix incompatibility with pip >= 10.0


## 1.1.0 (2018-04-17)

### Major changes

- Improve run form: add support for uploading an alignment file (PAF or MAF by default) instead of fasta files, if alignment file is already available
- Add export of a job into a backup, which can be re-uploaded with the run form
- Ease the integration of new tools or new file formats
- Allow to install as simple user on Unix systems

### Other changes

- Export of the dot plot is now done including the zoom factor
- Add new color palettes for dot plot
- Add analytics logs (anonymous) which permits to know which size of genomes are ploted (can be disabled)
- Improve documentation
- Minor bug fixes


## 1.0.1 (2018-02-23)

Bug fix release.

### Changes

- Fix bugs
- Disable export of fasta files for gallery items


## 1.0.0 (2018-02-21)

First stable release
