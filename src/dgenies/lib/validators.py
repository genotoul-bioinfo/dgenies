"""
Define formats validators here (for alignment files)

Each validator (main function) has a name which is exactly the name of the format in the aln-formats.yaml file.
Only 1 argument to this function:
- Input file to check

Secondary functions must start with _

Validators for non-mapping files must start with "v_"

Returns True if file is valid, else False
"""

from Bio import AlignIO
import os
import shutil
import traceback
from functools import reduce


def _good_paf_line(parts):
    """
    Check PAF line splitted in many parts

    :param parts: line splitted in many parts
    :type parts: list
    :return: True if line is correctly formatted
    :rtype: bool
    """
    result = len(parts) >= 12 \
        and reduce(lambda x, y: x and y, (z.isdigit() for z in parts[1:4])) \
        and parts[4] in ['+', '-'] \
        and reduce(lambda x, y: x and y, (z.isdigit() for z in parts[6:12])) \
        and 0 <= int(parts[11]) <= 255
    return result


def paf(in_file, n_max=None):
    """
    Paf validator

    :param in_file: paf file to test
    :type in_file: str
    :param n_max: number of lines to test (default: None for all)
    :type n_max: int
    :return: True if valid, else False
    :rtype: bool
    """
    try:
        with open(in_file, "r") as aln:
            n = 0
            for line in aln:
                parts = line.rstrip().split("\t")
                if not _good_paf_line(parts):
                    return False
                n += 1
                if n_max and n >= n_max:
                    break
    except:
        traceback.print_exc()
        return False
    else:
        return True


def _filter_maf(in_file):
    """
    Filter Maf file (remove unused lines)

    :param in_file: maf file to filter
    """
    new_file = in_file + ".new"
    with open(in_file, "r") as inf, open(new_file, "w") as new:
        for line in inf:
            if len(line.rstrip()) == 0 or line[0] in ["#", "a", "s"]:
                new.write(line)
    os.remove(in_file)
    shutil.move(new_file, in_file)


def maf(in_file):
    """
    Maf validator

    :param in_file: maf file to test
    :type in_file: str
    :return: True if valid, else False
    :rtype: bool
    """
    _filter_maf(in_file)
    try:
        maf = AlignIO.parse(in_file, "maf")
        for grp in maf:
            if len(grp) != 2:
                return False
    except:
        return False
    else:
        return True


def v_idx(in_file):
    """
    Index file validator

    :param in_file: index file to test
    :type in_file: str
    :return: True if valid, else False
    :rtype: bool
    """
    try:
        with open(in_file, "r") as inf:
            first_line = inf.readline()
            if "\t" in first_line:
                return False
            must_be_last = False
            for line in inf:
                if must_be_last:
                    return False
                line = line.rstrip()
                if line == "":
                    must_be_last = True
                else:
                    cols = line.split("\t")
                    if len(cols) != 2:
                        return False
                    if not cols[1].isdigit():
                        return False
    except:
        return False
    else:
        return True
