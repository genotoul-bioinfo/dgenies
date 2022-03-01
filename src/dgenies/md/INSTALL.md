# Run your own instance of D-Genies

{% if version != "" %}
Latest available version: **{{version}}**
{% endif %}

D-Genies is designed to run on Linux and Windows.
It may work on macOS, but this case is not tested.

D-Genies can be run in 2 modes. According to the mode you will run it, installation must be adapted :

- Standalone mode, for a single user on his own computer
- Webserver mode, for multiple users through a webserver, can be connected to a HPC for computation

Windows version of D-Genies is limited to standalone mode.

## Linux

### Requirements

D-Genies requires a 64 bits system with python >= 3.5 to run.

D-Genies uses Minimap2 and MashMap (v2.0) for mapping. An x86_64 binary of each of them is shipped with it.
Alternatively, you can install your own binaries from [Minimap2](https://github.com/lh3/minimap2) and [MashMap](https://github.com/marbl/MashMap/) repositories and tell D-Genies to use them by [editing executable paths in the `tools.yaml` file](#add-or-change-alignment-tools).

At the moment, all python modules listed below, except `mysqlclient`, are automatically installed by D-Genies regardless to the mode it will be run.
We list them for information purposes

#### Standalone mode

Following python modules are required in order to run D-Genies in standalone mode:

    biopython>=1.70
    Flask==1.0.*
    intervaltree==3.*
    Jinja2~=2.11.3
    Markdown>=2.6.*
    matplotlib>=2.1.*
    numpy
    psutil>=5.6.6
    pyyaml>=5.4.1
    requests>=2.20.1
    tendo==0.2.*

#### Webserver mode

Webserver mode uses some additional python modules:

    Flask-Mail==0.9.*
    peewee==3.*
    python-crontab>=2.2.*

D-Genies uses by default `sqlite` to store job states. In webserver mode, you may want to use a more performant RDBM engine.
D-Genies allows using `mysql` or `mariadb` as alternative to `sqlite`.
In this case you must install `mysqlclient` python module (that will not be installed automatically).

Webserver mode also requires the `time` executable located at `/usr/bin/time` to be installed (package `time` on debian or redhat based distributions).

#### Connection to a cluster (HPC)

D-Genies, in webserver mode, can use [`slurm`](https://slurm.schedmd.com/) job scheduler with [drmaa](https://github.com/natefoo/slurm-drmaa) capacities to compute heavy jobs.
It also works with `SGE`, but this later is not intensively tested.

If you like to connect D-Genies to a cluster, an additional module is required:

    drmaa==0.7.*

The [*Running with a cluster with* section](#running-with-a-cluster) will help you to configure D-Genies to run with your cluster.

### Installation

D-Genies can be installed in many ways:

- if you aim to run D-Genies in standalone mode, the installation with [conda](#install-with-conda) or with [pip as user](#install-with-pip) are recommended methods;
- if you aim to run D-Genies in webserver mode, the installation with [pip as root](#install-with-pip) or [from source](#install-from-source) may be more adapted.

#### Install with conda

If you want to run D-Genies in standalone mode, you can use [anaconda](https://www.anaconda.com/products/individual)/[miniconda](https://docs.conda.io/en/latest/miniconda.html)

    conda create -c conda-forge -c bioconda -n dgenies dgenies

#### Install with pip

`pip` is another easy way to install D-Genies. You can use this way to install D-Genies in a virtualenv.

**As simple user** (recommended for standalone mode):

    pip3 install --user dgenies

When installed as user, following configuration files are written in `~/.dgenies/` directory:

- `application.properties`
- `tools.yaml`
- `dgenies.wsgi`

**As root** (recommended for webserver mode):

    pip3 install dgenies

The installation process as root will create following configuration files:

- /etc/dgenies/application.properties
- /etc/dgenies/tools.yaml
- /var/www/dgenies/dgenies.wsgi

#### Install from source

Alternatively, you can install D-Genies manually from its source repository:

    git clone https://github.com/genotoul-bioinfo/dgenies
    cd dgenies
    pip3 install -r requirements.txt
    python3 setup.py install

### Upgrade

#### Standalone mode

    pip3 install dgenies --upgrade

Add `--user` flag if you have not root access.

#### Webserver mode

    dgenies clear -c
    pip3 install dgenies --upgrade

Then, you need to restart your webserver. This will restart D-Genies instance.

## Windows

### Requirements

You need Windows 7 or newer, 64 bits architecture.

### Installation

We provide an installer to install D-Genies. [Download it]({%if win32 %}{{win32}}{% else %}https://github.com/genotoul-bioinfo/dgenies/releases{% endif %}) and run it.

All requirements are present inside it, so you don't have to do anything else.

Only Minimap2 is provided with Windows version.

*Note: The installer is not signed. Microsoft Defender SmartScreen will throw a warning about it. You can still install D-Genies by clicking on "More info" and then "Run anyway".*

### Upgrade

Just install the new version above the old one.

## How to start

### Standalone mode

#### Linux

Start D-Genies with the command below:

    dgenies run

Optional arguments:

`-p <port>` run in a specified port (default: 5000)
`--no-browser` don't start the browser automatically

#### Windows 

You can launch D-Genies from Start menu, or double-click on the launcher present on the desktop (if chosen during the installation process) or into the installation folder.

### Webserver mode

*Note: this mode is only available for Unix systems and will NOT work on MS Windows.*

#### Recommended method

Flask webserver (which is used in standalone mode) is not recommended in production servers.
So, we recommend using the WSGI module of Apache (or µWSGI + nginx, not documented here).

Once D-Genies is installed, you just need to use the `/var/www/dgenies/dgenies.wsgi` file into your apache
virtualhost file.

Here is an example of configuration file for apache:

    <VirtualHost *>
        ServerName <url>

        WSGIDaemonProcess dgenies user=<user> group=<group> threads=8
        WSGIScriptAlias / /var/www/dgenies/dgenies.wsgi

        <Directory /var/www/dgenies>
            WSGIProcessGroup dgenies
            WSGIApplicationGroup %{GLOBAL}
            Order deny,allow
            Allow from all
        </Directory>
    </VirtualHost>

With:
`<url>`: the URL of your instance
`<user>`: the user who launch the server
`<group>`: the group who launch the server

#### Debug method

For debug or for development only, you can launch dgenies through flask in webserver mode:

    dgenies run -m webserver

Optional parameters:

`-d` run in debug mode
`-o <IP>` specify the host into run the application (default: 127.0.0.1, set 0.0.0.0 for distant access)
`-p <port>` run in a specified port (default: 5000)
`--no-crons` don't run the crons automatically
`--no-browser` don't start the browser automatically (always true if *-d* option is given)

You also need to run the D-Genies local scheduler

    src/dgenies/bin/local_scheduler.py -d "true"

## Running with a cluster

If you want to run jobs on a cluster, some configuration is required. We only support [`slurm`](https://slurm.schedmd.com/) and `SGE` schedulers. But please note that only `slurm` scheduler has been fully tested.

*Note: submitting jobs on a cluster is only available for webserver mode.*

Jobs are submitted through the `drmma` library. So you need it for your scheduler. Please see [the cluster configuration section](#cluster) to define path to this library.

Also, scripts for preparing data must be installed in a location accessible by all nodes of your cluster. You must put them in a same folder and set the full path to `all_prepare.py` script (full path on the nodes of the cluster) in the configuration file like described in [the cluster configuration section](#cluster).

You can get these scripts with the following commands:

    curl https://raw.githubusercontent.com/genotoul-bioinfo/dgenies/v{{version}}/get_cluster_scripts.py > get_cluster_scripts.py
    python get_cluster_scripts.py -d <dir>

Where `<dir>` is the folder where the scripts will be saved (must be accessible by cluster nodes).

## Configuration

Changing the default configuration is not required for standalone mode, but you may want to customize some parts of D-Genies.

Configuration file location:

- Linux:
  - `/etc/dgenies/application.properties` if installed with root access  
  - `~/.dgenies/application.properties` else  
- Windows:
  - `application.properties` file of the installation folder

A good practice, when editing the D-Genies configuration, is to copy `application.properties` to `application.properties.local` (at the same location), and modify `application.properties.local`. It avoids to erase of the file on upgrades.

The configuration file is divided in 9 sections described below.

### Global

Main parameters are stored into this section:

- `config_dir`: where configuration file will be stored.
- `upload_folder`: where uploaded files will be stored.
- `data_folder`: where data files will be stored (PAF files and other files used for the dotplot).
- `web_url`: public URL of your website.
- `max_upload_size`: max size allowed for query and target file (-1 to avoid the limit) - size uncompressed.
- `max_upload_size_ava`: max size allowed for target file for all-vs-all mode (only target given, -1 to avoid the limit) - size uncompressed.
- `max_upload_file_size`: max size of the uploaded size (real size of the file, compressed or not, -1 to avoid the limit).
- `max_nb_lines`: Maximum number of lines displayed for paf file (default: 100000).

For webserver mode only (ignored in standalone mode):

- `batch_system_type`: local for run all jobs locally, sge or slurm to use a cluster scheduler.

### Debug

Some parameters for debug:

- `enable`: True to enable debug
- `log_dir`: folder into store debug logs

### Cluster

This section concerns only the webserver mode with *batch_system_type* not set to *local*.

D-Genies is tested with [slurm-drmaa](https://github.com/natefoo/slurm-drmaa).

- `drmaa_lib_path`: absolute path to the drmaa library. Required as we use the DRMAA library to submit jobs to the cluster.
- `native_specs`: how to set memory, time and number of CPU on the cluster (should be kept as default).

By default, small jobs are still launched locally even if *batch_system_type* is not set to *local*, and if not too much of these jobs are running or waiting. This limit can be customized:

- `max_run_local`: max number of jobs running locally (if this number is reached, future jobs will be submitted to the cluster regardless of their size). Set to 0 to run all jobs on the cluster.
- `max_wait_local`; max number of jobs waiting for a local run (if this number is reached, future jobs will be submitted to the cluster regardless of their size). Set to 0 to run all jobs on the cluster.

You can also customize the size from which jobs are submitted on the cluster. If only one of these limit is reached, the job is submitted on the cluster.

- `min_query_size`: minimum size for the query (uncompressed).
- `min_size_target`: minimum size for the target (uncompressed).

Other parameters:

- `prepare_script`: absolute path to the all_prepare.py script downloaded in the section [above](#running-with-a-cluster).
- `python3_exec`: path to python3 executable on the cluster.
- `memory`: max memory to reserve on the cluster.
- `memory_ava`: max memory to reserve on the cluster in all-vs-all mode (should be higher than memory).

### Database

This section concerns only the webserver mode.

In webserver mode, we use a database to store jobs.

- `type`: sqlite or mysql. We recommend mysql for better performances.
- `url`: path to the sqlite file, or url to the mysql server (localhost if the mysql server is on the same machine).

If type is mysql, some other parameters must be filled:

- `port`: port to connect to mariadb or mysql (3306 as default).
- `db`: name of the database.
- `user`: username to connect to the database.
- `password`: the associated password.

### Mail

This section concerns only the webserver mode.

At the end of the job, a mail is sent to the user to advise him of the end of the job.

- `status`: mail to use for status mail.
- `reply`: mail to use as reply to.
- `org`: name of the organisation who send the mail.
- `send_mail_status`: True to send mail status, False else. Should be True in production.

### Cron

This section concerns only the webserver mode.

We use crons to launch the local scheduler who start jobs, and some script that clean old jobs.

- `clean_time`: time at which we launch the clean job (example: 1h00)
- `clean_freq`: frequency of the clean job execution in days

### Jobs

This section concerns only the webserver mode.

Several parameters for jobs:

- `run_local`: max number of concurrent jobs launched locally.
- `data_prepare`: max number of data prepare jobs launched locally.
- `max_concurrent_dl`: max number of concurrent upload of files allowed.

### Example

Here, you can fill example data. At least target is required to enable example data.

Fill for target and query the absolute local path of the file. This path will not be shown to the client. Only the file name will be shown.

If at least target is filled, a button "Load example" will be shown in the run form. Click on it will load example data in the form.

### Analytics

Set `enable_logging_runs` to True will enable storage of analytics data. It stores for each job creation date, user email, size of query and target, batch type, and tool used.

Since version 1.3.0, user email is anonymize by matching patterns defined in the `[analytics_groups]` section. If no match is found, the email is replaced by an empty string.

Set `disable_anonymous_analytics` to True will enable storage of email without anonymization like in previous versions.

### Analytics_groups

Groups for user email anonymization are defined by using the following syntax

- `<group> = <regex pattern>`

You can set as many group you want. The entry order is important. A user email can be only part of one group.
The first matched pattern will be used to assign the group. Groups are case-insensitive, whereas pattern are case-sensitive

**Example**

    [analytics_groups]
    INRAE = ^.*@inrae?\.fr$
    Other = ^.*$

### Legal

GDPR like laws ask to warn people about how privacy data are collected and used.
In webserver mode, you can use:

- `cookie_wall`: Set the message that will display by D-Genies in order to warn about cookies. If not set, nothing will be displayed.
As D-Genies only uses essential cookies, there is no way to refuse those cookies.
- `<page name> = /path/to/my/page.md`: Associate the `legal/<page name>` address to the related Markdown file. You can set as many pages you want.

**Example**


    [legal]
    cookie_wall = D-Genies uses essential cookies in order to work, as described in <a href='/legal/cookies'>Cookies policy page</a>.
    Cookies = src/dgenies/md/cookies.md


You can use the `src/dgenies/md/cookies.md` file as a model.

## Customize your installation

You can make easily make some changes to the application, described below. To do so, you must first clone the D-Genies repository (except if changes can be done in the current installation, see below):

    git clone https://github.com/genotoul-bioinfo/dgenies

The created folder is named the `D-Genies repository` in the text below.

Then, you make changes described below. When done, you can easily install the customized version with this command:

    pip install .

Add the `--upgrade` flag if you already have D-Genies installed.

### Add or change alignment tools

D-Genies uses minimap2 as default aligner, but you can add other tools, or replace minimap2 by another tool. You can also change minimap2 executable path.

If your tool needs a parser (see below), you must customize the installation (see above). For other changes, you can make them on your current installation.

Tools definition YAML file:

- Linux:
  - `/etc/dgenies/tools.yaml` if installed with root access  
  - `~/.dgenies/tools.yaml` else  
- Windows:
  - `tools.yaml` file of the installation folder

To change this file, please copy it into `tools.yaml.local` (at the same location) to avoid erasing the file on upgrades.

Note: you can also edit the `tools.yaml` file of the D-Genies repository, which will be installed then (if you customize the installation). Edit it without renaming it.

For each tool, you can or must define several properties described bellow.

#### Executable path

Required.

Always set tool binary path in the `exec` property. If it differs for cluster execution, set it in the `exec_cluster` property.

#### Executable path

Optional.

String displayed in aligner section in the run page for the given tool.

#### Command line skeleton

Required.

The command line skeleton defines how to launch the program, in the `command_line` property. The skeleton must include the following tags:
  
- `{exe}`: will be replaced by the executable path
- `{target}`: will be replaced by the target fasta file
- `{query}`: will be replaced by the query fasta file
- `{options}`: will be replaced by the options fields selected
- `{out}`: will be replaced by the output file

If the tool can be multithreaded, add the `{threads}` tag which will be replaced by the number of threads to use.

If your program is able to use all-vs-all mode (target versus itself), define the same skeleton in the `all_vs_all` property. All tag described hereover must be set except the `{query}` tag.

#### Threads

Required.

Defines how many threads to use for this tool. Set it in the `threads` property for local executions, and the `threads_cluster` property for cluster execution (if different from the local one).

#### Max memory

Optional.

If the tool requires less memory than defined in the configuration file, you can add the `max_memory` property. The unit is Gb.

#### Parser

Optional.

If the tool does not output PAF format, you must define a function in the `src/dgenies/lib/parsers.py` file of the D-Genies repository. This function get the input file as first parameter and outputs a valid PAF file (output file, second parameter). You must reference the function name in the `parser` property.

#### Split before

Optional. Default: False

For some tools (like minimap2), splitting the query on 10 Mb blocks improves performances (blocks are merged after mapping). To enable this for the tool, set the `split_before` property to True.

#### Help

Optional.

Define a message to show aside the tool name in the run form. Set it in the `help` property.

#### Order

Optional. Default: random.

Define in which order we show tools in the run form. Set it in the `order` property.

#### Options

Optional.

Define options displayed in form. List of individual options where each element of the list is defined as follows, displayed as they are ordered:

**Example** :

    options:
      -
        label: Repeatedness
        type: radio
        help: "Ignore top fraction of most frequent minimizers"
        entries:
          -
            label: "few repeats"
            value: "-f 0.0002"
            help: "-f 0.0002"
            default: True
          -
            label: "some repeats"
            value: "-f 0.002"
            help: "-f 0.002"
          -
            label: "many repeats"
            value: "-f 0.02"
            help: "-f 0.02"


##### Label

Required.

Text displayed in the form for the option

##### Type

Required.

Type of option. Either 'radio' or 'checklist'.

##### Help

Optional.

Define a message to show aside the option label in the run form. Set it in the `help` property.

##### Entries

List of choice allowed for the current option. Each entry must/can have the following keys:

###### Label

Required.

Text displayed in the form for the entry

###### Value

Required.

Command line parameter that will be used when the option is chosen.

###### Help

Optional.

Define a message to show aside the entry label in the run form. Set it in the `help` property.

###### Default

Optional. Default: False

Set it to true in order to have this entry enable by default.


### Add new formats

In `Plot alignment` mode in run form ([see here](/documentation/run#plot-alignment-mode)), we propose by default only PAF and MAF formats. It's easy to add new formats.

Just define 2 functions:

- Add the first one in the `src/dgenies/lib/validators.py` file of the D-Genies repository. It takes only one argument: the input file. It checks if the file format is correct and returns True in this case, else it returns False. The function name must be the same as the expected input file extension.  
- Add the second one in the `src/dgenies/lib/parsers.py` file of the D-Genies repository. It takes two arguments: the input and the output file. It converts the input file into a valid PAF file. The function name must be same as the previous one.

## Maintenance

The `dgenies` command can be used to do some maintenance staff.

**Clear all jobs:**

    dgenies clear -j [--max-age <age>]

`--max-age` (opt): set the max age of jobs to delete (default: 0, for all)

**Clear all jobs from analytics:**

    dgenies clear -a [--max-age <age>]

`--max-age` (opt): set the max age of jobs to delete (default: 0, for all)

**Clear all log:**

    dgenies clear -l

**Clear crons (webserver mode):**

    dgenies clear -c

**Display message on run form:**

You can display a message at the top of the run form. It can be used to add extra information for user, or for prevent him for problem or for a maintenance on your instance.

    dgenies inforun -m "message to display" -t [warn, critical, info, success]

`-m <message>`: message to display. Html allowed.  
`-t <type>`: type of message: warn (orange background), critical (red background), info (blue background) or success (green background).

Remove the message by:

    dgenies inforun -c

## Gallery

Note: gallery is only available in webserver mode.

To add a job to the gallery, copy illustrating picture file into the *gallery* folder inside the data folder (*~/.dgenies/data/gallery* as default, create it if not exists). Then use the *dgenies* command:

    dgenies gallery add -i <id_job> -n <name> -q <query_name> -t <target_name> -p <pict_filename>

With:
`id_job`: the name of the job
`name`: name of the job to show in the gallery
`query_name`: name of the query
`target_name`: name of the target
`pict_filename`: filename added in the gallery folder (without path)

You can also delete an item from the gallery:

    dgenies gallery del -i <id_job>

or:

    dgenies gallery del -n <name>

With `id_job` and `name` as described above. You can add the `--remove-pict` option to remove the picture file from the gallery folder.

Note: first item of the gallery will be shown on home page.
