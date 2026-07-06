import os
import shutil
import time
import re
import dgenies.lib.validators as validators
from .datafile import DataFile
from .functions import Functions
import requests
from requests.exceptions import ConnectionError
from urllib.request import urlretrieve
from urllib.error import URLError
import traceback
from pathlib import Path
import tarfile
from dgenies.lib.exceptions import DGeniesFileCheckError, DGeniesNotGzipFileError, DGeniesUploadedFileSizeLimitError, \
    DGeniesAlignmentFileUnsupported, DGeniesAlignmentFileInvalid, DGeniesIndexFileInvalid, \
    DGeniesURLError, DGeniesURLInvalid, DGeniesDistantFileTypeUnsupported, DGeniesDownloadError, \
    DGeniesBackupUnpackError

from dgenies import MODE
from dgenies.database import Job

if MODE == "webserver":
    from dgenies.database import Session


from .datafile_context import DataFileContextManager


class JobManagerFilesMixin:

    def _getting_local_file(self, datafile):
        """
        Copy temp file to its final location

        :param datafile: data file Object
        :type datafile: DataFile
        :return: final full path of the file
        :rtype: str
        """
        finale_path = os.path.join(self.output_dir, os.path.basename(datafile.get_path()))
        if datafile.is_example():
            shutil.copy(datafile.get_path(), finale_path)
        else:
            if os.path.exists(datafile.get_path()):
                shutil.move(datafile.get_path(), finale_path)
            else:
                raise Exception("Unable to copy file from temp to finale path: %s file does not exists" %
                                (datafile.get_path()))
        return finale_path

    def normalize_files(self):
        """
        Rename data file with prefix and create dotfiles
        """
        for type_f in self.allowed_ext.get_roles(self.get_job_type()):
            datafile = getattr(self, type_f)
            if datafile is not None:
                finale_path = os.path.join(self.output_dir, type_f + "_" + os.path.basename(datafile.get_path()))
                if os.path.exists(datafile.get_path()):
                    self.logger.debug("{} - Move {} to {}".format(self.id_job, datafile.get_path(), finale_path))
                    shutil.move(datafile.get_path(), finale_path)
                    datafile.set_path(finale_path)
                else:
                    raise Exception("Unable to normalize %s file: %s file does not exists" %
                                    (type_f, datafile.get_path()))

                # We create a "dot file" to store the file name for cluster
                with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
                    save_file.write(finale_path)

    def _get_filename_from_url(self, url):
        """
        Retrieve filename from an URL (http or ftp). Will raise DGeniesURLInvalid exception on error.

        :param url: url of the file to download
        :type url: str
        :return: filename
        :rtype: str
        """
        if url not in self._filename_for_url:
            if url.startswith("ftp://"):
                self._filename_for_url[url] = url.split("/")[-1]
            elif url.startswith("http://") or url.startswith("https://"):
                try:
                    r = requests.head(url, allow_redirects=True)
                    self._filename_for_url[url] = r.url.split("/")[-1]
                    if 'content-disposition' in r.headers:
                        fnames = re.findall(r'filename="(.+)"', r.headers['content-disposition'])
                        if fnames:
                            self._filename_for_url[url] = fnames[0]
                except (ConnectionError, URLError):
                    raise DGeniesURLInvalid(url)
            else:
                raise DGeniesURLInvalid(url)
        return self._filename_for_url[url]

    def _download_file(self, url):
        """
        Download a file from an URL

        :param url: url of the file to download
        :type url: str
        :return: distant file name and absolute path of the downloaded file
        :rtype: tuple of str
        """
        distant_filename = self._get_filename_from_url(url)
        # download in dedicated dir in order to avoid collision with working files.
        download_dir = os.path.join(self.output_dir, "download")
        if not os.path.exists(download_dir):
            os.mkdir(download_dir)
        # Manage file override
        local_path = os.path.join(download_dir, distant_filename)
        i = 1
        while os.path.exists(local_path):
            local_path = os.path.join(download_dir, "{:d}_".format(i) + distant_filename)
            i += 1
        # NOTE the stream=True parameter
        if url.startswith("ftp://"):
            urlretrieve(url, local_path)
        else:
            r = requests.get(url, stream=True)
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        # f.flush() commented by recommendation from J.F.Sebastian
        return distant_filename, local_path

    def _getting_file_from_url(self, datafile):
        """
        Download file from URL

        :param datafile: input file description
        :type datafile: DataFile
        :return:
            * [0] Finale path of the downloaded file {str}
            * [1] Name of the downloaded file {str}
        :rtype: tuple
        """
        try:
            distant_filename, dl_path = self._download_file(datafile.get_path())
        except (ConnectionError, URLError):
            raise DGeniesURLInvalid(datafile.get_path())
        name = os.path.splitext(os.path.basename(distant_filename).replace(".gz", ""))[0]
        return dl_path, name

    def _check_url(self, datafile, contexts):
        """
        Check if an URL is valid, and if the file is valid too. If invalid, raise an DGeniesURLError

        :param datafile: datafile file object
        :type datafile: DataFile
        :param contexts: list of contexts as (job type, file role) the datafile is used with
        :type contexts: list of tuple
        """
        url = datafile.get_path()
        filename = self._get_filename_from_url(url)
        for job_type, file_role in contexts:
            #logger.debug("{} - {}".format(self.id_job, file_role))
            formats = self.allowed_ext.get_formats(job_type, file_role)
            allowed = Functions.allowed_file(filename, tuple(formats))
            if not allowed:
                format_descriptions = [self.allowed_ext.get_description(f) for f in formats]
                raise DGeniesDistantFileTypeUnsupported(filename, url, format_descriptions)

    def clear(self):
        """
        Remove job dir
        """
        shutil.rmtree(self.output_dir)

    @staticmethod
    def get_pending_local_number():
        """
        Get number of jobs running or waiting for a run

        :return: number of jobs
        :rtype: int
        """
        if MODE == "webserver":
            with Job.connect():
                return len(Job.select().where((Job.runner_type == "local") & (Job.status != "success") &
                                              (Job.status != "fail") & (Job.status != "no-match")))
        else:
            return 0

    def check_file(self, datafile, input_type, size_limit, should_be_local):
        """
        Check if file is correct: format, size, valid gzip, will raise a DGeniesFileCheckError Exception on error
        Will set the size attribute of datafile

        :param datafile: file to check
        :type datafile: DataFile
        :param input_type: query, target, align, backup or batch
        :type input_type: str
        :param size_limit: limit of file size
        :type size_limit: int
        :param should_be_local: True if job should be treated locally
        :type should_be_local: bool
        :return: True if should be local, False else
        :rtype: bool
        """
        self.logger.info('{} - Check file: {}'.format(self.id_job, datafile.get_path()))
        max_upload_size_readable = size_limit / 1024 / 1024
        with Job.connect():
            if datafile.get_path().endswith(".gz") and not Functions.is_gz_file(datafile.get_path()):
                # Check file is correctly gzipped
                raise DGeniesNotGzipFileError(input_type)
            # Check size:
            file_size = self.get_file_size(datafile.get_path())
            datafile.set_file_size(file_size)
            if -1 < size_limit < file_size:
                raise DGeniesUploadedFileSizeLimitError(datafile.get_name(), max_upload_size_readable, unit="Mb",
                                                        compressed=False)

            if input_type == "align":
                aln_format = self.get_align_format(datafile.get_path())
                if not hasattr(validators, aln_format):
                    raise DGeniesAlignmentFileUnsupported()
                if not getattr(validators, aln_format)(datafile.get_path()):
                    raise DGeniesAlignmentFileInvalid()
            elif input_type not in ("backup", "batch"):
                if datafile.get_path().endswith(".idx"):
                    if not validators.v_idx(datafile.get_path()):
                        raise DGeniesIndexFileInvalid(input_type.capitalize())
                if self.config.runner_type != "local" and file_size >= getattr(self.config, "min_%s_size" % input_type):
                    should_be_local = False
        self.logger.info('{} - Done check file: {}'.format(self.id_job, datafile.get_path()))

        return should_be_local

    def download_files_with_pending(self, datafiles_with_contexts, should_be_local):
        """
        Download files from URLs, with pending (according to the max number of concurrent downloads)

        :param datafiles_with_contexts: datafiles with contexts.
        :type datafiles_with_contexts: DataFileContextManager
        :param should_be_local: True if the job should be run locally (according to input file sizes), else False
        :type should_be_local: bool
        :return: True if the job should be run locally according to file local, False else
        :rtype: bool
        """
        with Job.connect():
            status = "getfiles-waiting"
            if MODE == "webserver":
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                job.save()
                # Create a session:
                s_id = Session.new(True)
                session = Session.get(s_id=s_id)
            else:
                status = "getfiles"
                session = None
                job = None
                s_id = None

            try:
                if MODE == "webserver":
                    allowed = session.ask_for_upload(True)
                    while not allowed:
                        time.sleep(15)
                        session = Session.get(s_id=s_id)
                        allowed = session.ask_for_upload(False)
                else:
                    allowed = True
                if allowed:
                    if MODE == "webserver":
                        job.status = "getfiles"
                        job.save()

                    # download each distant file
                    for datafile in datafiles_with_contexts.get_datafiles():
                        if datafile.get_type() != "local":
                            self.logger.info("{} - Download file: {}".format(self.id_job, datafile.get_path()))
                            finale_path, filename = self._getting_file_from_url(datafile)  # Raise exception on error
                            datafile.set_path(finale_path)
                            datafile.set_name(filename)
                            datafile.set_type("local")
                            # Check file
                            for file_role, size_limit in datafiles_with_contexts.get_distinct(datafile, 'file_role', 'size_limit'):
                                should_be_local = self.check_file(datafile, file_role, size_limit, should_be_local)

            except (DGeniesFileCheckError, DGeniesURLError) as e:
                if MODE == "webserver":
                    session.delete_instance()
                # We propagate known errors (else will be catch with next except
                raise e

            except:
                # Except all possible exceptions, but in particular session disappearance on timeout
                traceback.print_exc()
                if MODE == "webserver":
                    session.delete_instance()
                raise DGeniesDownloadError

            if MODE == "webserver":
                session.delete_instance()
            return should_be_local

    def move_and_check_local_files(self, datafiles_with_contexts):
        """
        Move local file from tmp and check files (both local files and distant files)
        Raise DGeniesFileCheckError or DGeniesURLError on error

        :params datafiles_with_contexts: Datafiles with contexts (job type, file type, file size, ...) they apply to
        :type: DataFileContextManager
        :return: True if the job should be run locally according to file local, False else
        :rtype: bool
        """
        should_be_local = True
        for datafile in datafiles_with_contexts.get_datafiles():
            if datafile.get_type() == "local":
                # Move local files from tmp and check them
                datafile.set_path(self._getting_local_file(datafile))
                for file_role, size_limit in datafiles_with_contexts.get_distinct(datafile, 'file_role', 'size_limit'):
                    should_be_local = self.check_file(datafile, file_role, size_limit, should_be_local)
            else:
                contexts = datafiles_with_contexts.get_distinct(datafile, 'job_type', 'file_role')
                self.logger.debug(contexts)
                self._check_url(datafile, contexts)  # Will raise an exception on error
        return should_be_local

    @staticmethod
    def allowed_backup_files(members, allowed_files=[], ignored_files=[]):
        """
        Generator filter files to be extracted from tar file

        :param members: elements in tarfile
        :type members: list of TarInfo
        :param allowed_files: list of allows files
        :type allowed_files: list of str
        """
        for tarinfo in members:
            if tarinfo.name in allowed_files and tarinfo.name not in ignored_files:
                yield tarinfo

    def _unpack_backup(self, backup: DataFile, output_dir):
        """
        Unpack backup file. A backup file must contain 3 files: "./map.paf", "./query.idx" and "./target.idx".
        Will raise a DGeniesBackupUnpackError exception if file is not valid or on extraction error.

        :param backup: backup file to unpack
        :type backup: DataFile
        :param output_dir: Directory where to unpack backup
        :type output_dir: str or Path
        :return: a triplet of datafiles
            *[0]: query Datafile for "query.idx"
            *[1]: target Datafile for "target.idx"
            *[3]: align Datafile for "map.paf"
        :rtype: tuple
        """
        allowed_files = {"map.paf", "query.idx", "target.idx", "logs.txt"}
        ignored_files = {"logs.txt"}
        try:
            with tarfile.open(backup.get_path(), "r:*") as tar:
                members = tar.getmembers()
                if not(3 <= len(members) <= 4):
                    raise DGeniesBackupUnpackError()
                for m in members:
                    if m.name not in allowed_files or not m.isfile():
                        raise DGeniesBackupUnpackError()
                tar.extractall(path=output_dir, members=self.allowed_backup_files(tar, allowed_files, ignored_files))
                align_path = os.path.join(output_dir, "map.paf")
                if not validators.paf(align_path):
                    raise DGeniesBackupUnpackError()
                target_path = os.path.join(output_dir, "target.idx")
                query_path = os.path.join(output_dir, "query.idx")
                if not validators.v_idx(target_path) or not validators.v_idx(query_path):
                    raise DGeniesBackupUnpackError()
                align = DataFile(name="map", path=align_path, type_f="local")
                target = DataFile(name="target", path=target_path, type_f="local")
                query = DataFile(name="query", path=query_path, type_f="local")
            return query, target, align
        except:
            traceback.print_exc()
            raise DGeniesBackupUnpackError()

    def unpack_backups(self, datafiles_with_contexts):
        """
        Unpack all backup files (if any) and update associated job. Backup files are deleted if not used as anything
        else in other jobs.
        On error raise an DGeniesBackupUnpackError exception.

        :params datafiles_with_contexts: Collection of datafiles with associated contexts
        :params datafiles_with_contexts: DataFileContextManager
        """
        try:
            for datafile in datafiles_with_contexts.get_datafiles():
                if ("backup",) in datafiles_with_contexts.get_distinct(datafile, 'file_role'):
                    self.logger.info("{} - Unpack backup file {} ...".format(self.id_job, datafile.get_path()))
                    output_dir = os.path.join(self.output_dir,
                                              os.path.splitext(re.sub(r"\.gz$", "", datafile.get_path()))[0])
                    os.mkdir(output_dir)
                    query, target, align = self._unpack_backup(datafile, output_dir)
                    # Remove backup datafiles
                    removed_ctx = datafiles_with_contexts.remove(datafile, file_role="backup")
                    # Add the extracted datafiles and update jobs
                    for ctx in removed_ctx:
                        # remove batch file from jobs it appears in
                        ctx.job.unset_role('backup')
                        # add decompressed datafiles into jobs in which they are used
                        for role, new_datafile in [("align", align), ("query", query), ("target", target)]:
                            new_ctx = ctx.clone()
                            new_ctx.file_role = role
                            new_ctx.job.set_role(role, new_datafile)
                            datafiles_with_contexts.add(new_datafile, new_ctx)
                    self.logger.info("{} - Unpack backup file {} OK".format(self.id_job, datafile.get_path()))

                if not datafiles_with_contexts.get_distinct(datafile, 'file_role'):
                    # File is not used anywhere else, we remove it
                    os.remove(datafile.get_path())
        except DGeniesBackupUnpackError as e:
            raise e


    def distribute_files(self, datafiles_with_contexts):
        """
        Copy datafile in subjob directory, duplicate datafile and update subjob.
        Set file '.should_not_be_local' to flag if a job shouldn't be local
        """
        for datafile in datafiles_with_contexts.get_datafiles():
            for job, file_role in datafiles_with_contexts.get_distinct(datafile, 'job', 'file_role'):
                new_path = os.path.join(job.output_dir, os.path.basename(datafile.get_path()))
                if new_path != datafile.get_path():
                    # File is not in right place
                    n = 2
                    while os.path.exists(new_path):
                        new_path = os.path.join(job.output_dir, "{}_".format(n) + os.path.basename(datafile.get_path()))
                        n += 1
                    self.logger.info("{i} - Hardlink/copy {f} to {j}...".format(i=self.id_job, f=datafile.get_path(), j=new_path))
                    Functions.hardlink_or_copy(datafile.get_path(), new_path)
                new_datafile = datafile.clone()
                new_datafile.set_path(new_path)
                job.set_role(file_role, new_datafile)
                # subjob._write_job()
                if MODE == "webserver" and job.config.runner_type != "local" \
                        and hasattr(job.config, "min_%s_size" % file_role) \
                        and datafile.get_file_size() >= getattr(job.config, "min_%s_size" % file_role):
                    # We set a flag to tell job must run on cluster
                    Path(os.path.join(job.output_dir, '.should_not_be_local')).touch()
        # os.remove(datafile.get_path())  # We remove unneeded files from batch dir

    def start_job(self):
        """
        Start job: download, check and parse input files
        """
        with Job.connect():
            status = "getfiles"
            if MODE == "webserver":
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                job.save()
            else:
                job = None
                self.set_status_standalone(status)
            try:
                if os.path.exists(os.path.join(self.output_dir, '.already_checked')):
                    self.logger.info("{} - Files already checked, skipping file checking".format(self.id_job))
                else:
                    if self.is_batch():
                        jobs = self.batch
                    else:
                        jobs = [self]
                    dcm = DataFileContextManager(jobs)

                    self.logger.info("{} - Check local files...".format(self.id_job))
                    # Will raise a DGeniesFileCheckError or DGeniesURLError on error
                    self.move_and_check_local_files(dcm)
                    self.logger.info("{} - Check local files: OK".format(self.id_job))

                    # Some files may be downloaded
                    # Will raise a DGeniesURLError, DGeniesDownloadError or DGeniesFileCheckError on error
                    self.logger.info("{} - Download distant files...".format(self.id_job))
                    self.download_files_with_pending(dcm, True)
                    self.logger.info("{} - Download distant files: OK".format(self.id_job))

                    # unpack backup files if any
                    self.unpack_backups(dcm)

                    # Move and check datafile in working dir
                    self.logger.info("{} - Distribute file into job(s)...".format(self.id_job))
                    self.distribute_files(dcm)
                    # We copy datafile in subjob directory, duplicate datafile and update subjob
                    self.logger.info("{} - Distribute file into job(s): OK".format(self.id_job))

                    for j in jobs:
                        self.logger.info("{} - Normalize files for job: {}".format(self.id_job, j.id_job))
                        j.normalize_files()
                        self.logger.info("{} - Done normalize files in job: {}".format(self.id_job, j.id_job))
                        # We set a flag to tell the files of subjob are already checked
                        Path(os.path.join(j.output_dir, '.already_checked')).touch()

                    # Backup jobs with params for next batch step in standalone mode.
                    if self.is_batch():
                        self.write_jobs(jobs)

                # Set the runner according to available resources
                should_be_local = not os.path.exists(os.path.join(self.output_dir, '.should_not_be_local'))
                self.logger.debug("{} - Job should be local: {}".format(self.id_job, should_be_local))
                if MODE == "webserver" and job.runner_type != "local" and should_be_local \
                        and self.get_pending_local_number() < self.config.max_run_local:
                    self.logger.debug("{} - Set runner from {} to {}".format(self.id_job, job.runner_type, "local"))
                    job.runner_type = "local"
                    job.save()

            except (DGeniesFileCheckError, DGeniesURLError, DGeniesDownloadError) as e:
                self.set_job_status("fail", e.message)
                self._save_analytics_data()
                self._set_analytics_job_status("fail-getfiles")
                if e.clear_job:
                    self.clear()

            except DGeniesBackupUnpackError as e:
                self.set_job_status("fail", e.message)
                self._save_analytics_data()
                self.send_mail_if_allowed()
                if e.clear_job:
                    self.clear()

            except Exception:
                traceback.print_exc()
                error = "<p>An unexpected error has occurred while getting the files. Please contact the support to " \
                        "report the bug.</p> "
                self.set_job_status("fail", error)
                self._save_analytics_data()
                self._set_analytics_job_status("fail-getfiles")
                self.send_mail_if_allowed()

            else:
                self._save_analytics_data()
                # Prepare job for next step
                status = "waiting"
                if MODE == "webserver":
                    # Register job for next step
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.save()
                else:
                    # Start next step
                    self.set_status_standalone(status)
                    self.prepare_job_in_thread()
