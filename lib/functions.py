import os
import random
import string
import gzip
import io
import shutil
import sys
import re
import traceback
from lib.Fasta import Fasta
from collections import OrderedDict
from Bio import SeqIO
from jinja2 import Template
from config_reader import AppConfigReader
from database import Job
from pony.orm import db_session

ALLOWED_EXTENSIONS = ['fa', 'fasta', 'fna', 'fa.gz', 'fasta.gz', 'fna.gz']


class Functions:

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
    def index_file(fasta: Fasta, out):
        has_header = False
        next_header = False  # True if next line must be a header line
        compressed = fasta.get_path().endswith(".gz")
        with (gzip.open(fasta.get_path()) if compressed else open(fasta.get_path())) as in_file, \
                open(out, "w") as out_file:
            out_file.write(fasta.get_name() + "\n")
            with (io.TextIOWrapper(in_file) if compressed else in_file) as fasta:
                contig = None
                len_c = 0
                for line in fasta:
                    line = line.strip("\n")
                    if re.match(r"^>.+", line) is not None:
                        has_header = True
                        next_header = False
                        if contig is not None:
                            if len_c > 0:
                                out_file.write("%s\t%d\n" % (contig, len_c))
                            else:
                                return False
                        contig = re.split("\s", line[1:])[0]
                        len_c = 0
                    elif len(line) > 0:
                        if next_header or re.match(r"^[ATGCKMRYSWBVHDXN.\-]+$", line.upper()) is None:
                            return False
                        len_c += len(line)
                    elif len(line) == 0:
                        next_header = True

                if contig is not None and len_c > 0:
                    out_file.write("%s\t%d\n" % (contig, len_c))

        return has_header

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
                fasta_file = save_name.readline()
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
    @db_session
    def get_mail_for_job(id_job):
        j1 = Job.get(id_job=id_job)
        return j1.email

    @staticmethod
    def send_fasta_ready(mailer, job_name, sample_name, compressed=False):
        config = AppConfigReader()
        web_url = config.web_url
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates", "dl_fasta.html")) \
                as t_file:
            template = Template(t_file.read())
            message_html = template.render(job_name=job_name, status="success", url_base=web_url,
                                           sample_name=sample_name, compressed=compressed)
        message = "D-Genies\n\n" \
                  "Job %s - Download fasta\n\n" % job_name
        message += "Query fasta file for job %s (query: %s) is ready to download.\n" % (job_name, sample_name)
        message += "You can click on the link below to download it:\n\n"
        message += "%s/fasta-query/%s/%s" % (web_url, job_name, sample_name + ".fasta" + (".gz" if compressed else ""))
        mailer.send_mail([Functions.get_mail_for_job(job_name)], "Job %s - Download fasta" % job_name, message,
                         message_html)

    @staticmethod
    def sort_fasta(job_name, fasta_file, index_file, lock_file, compress=False, mailer=None):
        index, sample_name = Functions.read_index(index_file)
        is_compressed = fasta_file.endswith(".gz")
        if is_compressed:
            fasta_file = Functions.uncompress(fasta_file)
        seq = SeqIO.index(fasta_file, "fasta")
        fasta_file_o = fasta_file + ".sorted"
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
        if is_compressed:
            os.remove(fasta_file)
        if compress:
            Functions.compress(fasta_file_o)
        os.remove(lock_file)
        if mailer is not None and not os.path.exists(lock_file + ".pending"):
            Functions.send_fasta_ready(mailer, job_name, sample_name, compress)

    @staticmethod
    def compress_and_send_mail(job_name, fasta_file, index_file, lock_file, compressed, mailer):
        Functions.compress(fasta_file)
        os.remove(lock_file)
        index, sample_name = Functions.read_index(index_file)
        Functions.send_fasta_ready(mailer, job_name, sample_name, compressed)
