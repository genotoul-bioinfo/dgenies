import os
import random
import string
import gzip
import io
import re
from lib.Fasta import Fasta

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
        compressed = fasta.get_path().endswith(".gz")
        with (gzip.open(fasta.get_path()) if compressed else open(fasta.get_path())) as in_file, \
                open(out, "w") as out_file:
            out_file.write(fasta.get_name() + "\n")
            with (io.TextIOWrapper(in_file) if compressed else in_file) as fasta:
                contig = None
                len_c = 0
                for line in fasta:
                    line = line.strip("\n")
                    if line.startswith(">"):
                        if contig is not None:
                            out_file.write("%s\t%d\n" % (contig, len_c))
                        contig = re.split("\s", line[1:])[0]
                        len_c = 0
                    elif len(line) > 0:
                        len_c += len(line)
                if contig is not None and len_c > 0:
                    out_file.write("%s\t%d\n" % (contig, len_c))