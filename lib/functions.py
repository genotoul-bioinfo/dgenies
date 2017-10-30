import os
import random
import string

ALLOWED_EXTENSIONS = ['fa', 'fasta', 'fna', 'fa.gz', 'fasta.gz', 'fna.gz']


def allowed_file(filename):
    return '.' in filename and \
           (filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or ".".join(filename.rsplit('.', 2)[1:]).lower()
            in ALLOWED_EXTENSIONS)


def random_string(s_len):
    """
    Generate a random string
    :param s_len: length of the string to generate
    :return: the random string
    """
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(s_len)])


def get_valid_uploaded_filename(filename, folder):
    file_query_s = os.path.join(folder, filename)
    i = 2
    filename_orig = filename
    while os.path.exists(file_query_s):
        filename = str(i) + "_" + filename_orig
        file_query_s = os.path.join(folder, filename)
        i += 1
    return filename
