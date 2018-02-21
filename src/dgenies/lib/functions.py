import os
import random
import string
import gzip
import shutil
import sys
import re
import traceback
from collections import OrderedDict
from Bio import SeqIO
from jinja2 import Template
from dgenies.config_reader import AppConfigReader

ALLOWED_EXTENSIONS = ['fa', 'fasta', 'fna', 'fa.gz', 'fasta.gz', 'fna.gz']


class Functions:

    config = AppConfigReader()

    @staticmethod
    def allowed_file(filename):
        return '.' in filename and \
               (filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or ".".join(filename.rsplit('.', 2)[1:]).lower()
                in ALLOWED_EXTENSIONS)

    @staticmethod
    def random_string(s_len):
        """
        Generate a random string
        :param s_len: length of the string to generate
        :return: the random string
        """
        return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(s_len)])

    @staticmethod
    def get_valid_uploaded_filename(filename, folder):
        file_query_s = os.path.join(folder, filename)
        i = 2
        filename_orig = filename
        while os.path.exists(file_query_s):
            filename = str(i) + "_" + filename_orig
            file_query_s = os.path.join(folder, filename)
            i += 1
        return filename

    @staticmethod
    def __get_do_sort(fasta, is_sorted):
        do_sort = False
        if is_sorted:
            do_sort = True
            if fasta.endswith(".sorted"):
                do_sort = False
        return do_sort

    @staticmethod
    def get_fasta_file(res_dir, type_f, is_sorted):
        fasta_file = None
        try:
            with open(os.path.join(res_dir, "." + type_f), "r") as save_name:
                fasta_file = save_name.readline().strip("\n")
        except IOError:
            print(res_dir + ": Unable to load saved name for " + type_f, file=sys.stderr)
            pass
        if fasta_file is not None and os.path.exists(fasta_file):
            fasta_file_uc = fasta_file
            if fasta_file.endswith(".gz"):
                fasta_file_uc = fasta_file[:-3]
            if is_sorted:
                sorted_fasta = fasta_file_uc + ".sorted"
                if os.path.exists(sorted_fasta):
                    fasta_file = sorted_fasta
                else:
                    sorted_fasta = fasta_file_uc + ".gz.sorted"
                    if os.path.exists(sorted_fasta):
                        fasta_file = sorted_fasta

        return fasta_file

    @staticmethod
    def uncompress(filename):
        try:
            uncompressed = filename.rsplit('.', 1)[0]
            parts = uncompressed.rsplit("/", 1)
            file_path = parts[0]
            basename = parts[1]
            n = 2
            while os.path.exists(uncompressed):
                uncompressed = "%s/%d_%s" % (file_path, n, basename)
                n += 1
            with open(filename, "rb") as infile, open(uncompressed, "wb") as outfile:
                outfile.write(gzip.decompress(infile.read()))
            return uncompressed
        except Exception as e:
            print(traceback.format_exc())
            return None

    @staticmethod
    def compress(filename):
        try:
            if not filename.endswith(".gz") and not filename.endswith(".gz.sorted"):
                compressed = filename + ".gz" if not filename.endswith(".sorted") else filename[:-7] + ".gz.sorted"
                parts = compressed.rsplit("/", 1)
                file_path = parts[0]
                basename = parts[1]
                n = 2
                while os.path.exists(compressed):
                    compressed = "%s/%d_%s" % (file_path, n, basename)
                    n += 1
                with open(filename, "rb") as infile, gzip.open(compressed, "wb") as outfile:
                    shutil.copyfileobj(infile, outfile)
                os.remove(filename)
                return compressed
            return filename
        except Exception as e:
            print(traceback.format_exc())
            return None

    @staticmethod
    def read_index(index_file):
        index = OrderedDict()
        with open(index_file, "r") as index_f:
            # Sample name without special chars:
            sample_name = re.sub('[^A-Za-z0-9_\-.]+', '', index_f.readline().strip("\n").replace(" ", "_"))
            for line in index_f:
                if line != "":
                    parts = line.strip("\n").split("\t")
                    name = parts[0]
                    lenght = int(parts[1])
                    to_reverse = parts[2] == "1" if len(parts) >= 3 else False
                    index[name] = {
                        "length": lenght,
                        "to_reverse": to_reverse
                    }
        return index, sample_name

    @staticmethod
    def get_mail_for_job(id_job):
        from dgenies.database import Job
        with Job.connect():
            j1 = Job.get(Job.id_job == id_job)
            return j1.email

    @staticmethod
    def send_fasta_ready(mailer, job_name, sample_name, compressed=False, path="fasta-query", status="success",
                         ext="fasta"):
        web_url = Functions.config.web_url
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates", "dl_fasta.html")) \
                as t_file:
            template = Template(t_file.read())
            message_html = template.render(job_name=job_name, status=status, url_base=web_url,
                                           sample_name=sample_name, compressed=compressed, path=path, ext=ext)
        message = "D-Genies\n\n" \
                  "Job %s - Download fasta\n\n" % job_name
        message += "Query fasta file for job %s (query: %s) is ready to download.\n" % (job_name, sample_name)
        message += "You can click on the link below to download it:\n\n"
        message += "%s/fasta-query/%s/%s" % (web_url, job_name, sample_name + ".fasta" + (".gz" if compressed else ""))
        mailer.send_mail([Functions.get_mail_for_job(job_name)], "Job %s - Download fasta" % job_name, message,
                         message_html)



    @staticmethod
    def sort_fasta(job_name, fasta_file, index_file, lock_file, compress=False, mailer=None, mode="webserver"):
        index, sample_name = Functions.read_index(index_file)
        is_compressed = fasta_file.endswith(".gz")
        if is_compressed:
            fasta_file = Functions.uncompress(fasta_file)
        fasta_file_o = fasta_file + ".sorted"
        seq = SeqIO.index(fasta_file, "fasta")
        with open(fasta_file_o, "w") as fasta_out:
            for name, props in index.items():
                sequence = seq[name]
                if props["to_reverse"]:
                    s_id = sequence.id
                    s_name = sequence.name
                    s_description = sequence.description
                    sequence = sequence.reverse_complement()
                    sequence.id = s_id
                    sequence.name = s_name
                    sequence.description = s_description
                SeqIO.write(sequence, fasta_out, "fasta")
        seq.close()
        if is_compressed:
            os.remove(fasta_file)
        if compress:
            Functions.compress(fasta_file_o)
        os.remove(lock_file)
        if mode == "webserver" and mailer is not None and not os.path.exists(lock_file + ".pending"):
            Functions.send_fasta_ready(mailer, job_name, sample_name, compress)

    @staticmethod
    def compress_and_send_mail(job_name, fasta_file, index_file, lock_file, compressed, mailer):
        Functions.compress(fasta_file)
        os.remove(lock_file)
        index, sample_name = Functions.read_index(index_file)
        Functions.send_fasta_ready(mailer, job_name, sample_name, compressed)

    @staticmethod
    def get_readable_size(size, nb_after_coma=1):
        print(size)
        units = ["b", "Kb", "Mb", "Gb"]
        i = 0
        while size >= 1024 and i < 3:
            size /= 1024.0
            i += 1
        return str("%." + str(nb_after_coma) + "f %s") % (size, units[i])

    @staticmethod
    def get_readable_time(seconds):
        time_r = "%d s" % seconds
        if seconds >= 60:
            minutes = seconds // 60
            seconds = seconds - (minutes * 60)
            time_r = "%d min %d s" % (minutes, seconds)
            if minutes >= 60:
                hours = minutes // 60
                minutes = minutes - (hours * 60)
                time_r = "%d h %d min %d s" % (hours, minutes, seconds)
        return time_r



    @staticmethod
    def get_gallery_items():
        from dgenies.database import Gallery
        items = []
        for item in Gallery.select():
            items.append({
                "name": item.name,
                "id_job": item.job.id_job,
                "picture": item.picture,
                "query": item.query,
                "target": item.target,
                "mem_peak": Functions.get_readable_size(item.job.mem_peak),
                "time_elapsed": Functions.get_readable_time(item.job.time_elapsed)
            })
        return items

    @staticmethod
    def is_in_gallery(id_job, mode="webserver"):
        if mode == "webserver":
            from dgenies.database import Gallery, Job
            from peewee import DoesNotExist
            try:
                return len(Gallery.select().where(Gallery.job == Job.get(id_job=id_job))) > 0
            except DoesNotExist:
                return False
        return False

    @staticmethod
    def get_list_all_jobs(mode="webserver"):
        if mode == "webserver":
            return []  # Don't give the list in webserver as it's multi-user
        all_jobs = os.listdir(Functions.config.app_data)
        if "gallery" in all_jobs:
            all_jobs.remove("gallery")
        return sorted(all_jobs, key=lambda x: x.lower())
