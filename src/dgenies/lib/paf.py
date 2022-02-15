#!/usr/bin/env python3

from dgenies import MODE

import os
import shutil
from math import sqrt
from numpy import mean
from pathlib import Path
import json
from dgenies.bin.index import Index
from dgenies.config_reader import AppConfigReader
from dgenies.lib.functions import Functions
from intervaltree import IntervalTree
import matplotlib as mpl
mpl.use('Agg')
from matplotlib import pyplot as plt
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


class Paf:
    """
    Functions applied to PAF files
    """
    config = AppConfigReader()
    limit_idy = [0.25, 0.5, 0.75]
    max_nb_lines = config.max_nb_lines

    def __init__(self, paf: str, idx_q: str, idx_t: str, auto_parse: bool=True, mailer=None, id_job=None):
        """

        :param paf: PAF file path
        :type paf: str
        :param idx_q: query index file path
        :type idx_q: str
        :param idx_t: target index file path
        :type idx_t: str
        :param auto_parse: if True, parse PAF file at initialisation
        :type auto_parse: bool
        :param mailer: mailer object, to send mails
        :type mailer: Mailer
        :param id_job: job id
        :type id_job: str
        """
        self.paf = paf
        self.idx_q = idx_q
        self.idx_t = idx_t
        self.sorted = False
        self.data_dir = os.path.dirname(paf)
        if os.path.exists(os.path.join(self.data_dir, ".sorted")):
            self.paf += ".sorted"
            self.idx_q += ".sorted"
            self.sorted = True
        self.sampled= False
        self.len_q = None
        self.len_t = None
        self.min_idy = None
        self.max_idy = None
        self.lines = {}
        self.q_contigs = {}
        self.q_order = []
        self.t_contigs = {}
        self.t_order = []
        self.q_reversed = {}
        self.name_q = None
        self.name_t = None
        self.parsed = False
        self.error = False
        self.mailer = mailer
        self.id_job = id_job
        self.q_abs_start = {}
        self.t_abs_start = {}

        if auto_parse:
            self.parse_paf()

    @staticmethod
    def _flush_blocks(index_c, new_index_c, new_index_o, current_block):
        """
        When parsing index, build a mix of too small sequential contigs (if their number exceed 5), else just add
        co to the new index

        :param index_c: current index contigs def
        :type index_c: dict
        :param new_index_o: new index contigs order
        :type new_index_o: list
        :param new_index_c: new index contigs def
        :type new_index_c: dict
        :param current_block: contigs in the current analyzed block
        :type current_block: list
        :return: (new index contigs defs, new index contigs order)
        :rtype: (dict, list)
        """
        if len(current_block) >= 5:
            block_length = 0
            for contig in current_block:
                block_length += index_c[contig]
            b_name = "###MIX###_" + "###".join(current_block)
            new_index_c[b_name] = block_length
            new_index_o.append(b_name)
        elif len(current_block) > 0:
            for b_name in current_block:
                new_index_c[b_name] = index_c[b_name]
                new_index_o.append(b_name)
        return new_index_c, new_index_o

    def parse_index(self, index_o: list, index_c: dict, full_len: int):
        """
        Parse index and merge too small contigs together

        :param index_o: index contigs order
        :type index_o: list
        :param index_c: index contigs def
        :type index_c: dict
        :param full_len: length of the sequence
        :type full_len: int
        :return: (new contigs def, new contigs order)
        :rtype: (dict, list)
        """
        new_index_o = []
        new_index_c = {}
        current_block = []
        for index in index_o:
            if index_c[index] >= 0.002 * full_len:
                new_index_c, new_index_o = self._flush_blocks(index_c, new_index_c, new_index_o, current_block)
                current_block = []
                new_index_c[index] = index_c[index]
                new_index_o.append(index)
            else:
                current_block.append(index)
        new_index_c, new_index_o = self._flush_blocks(index_c, new_index_c, new_index_o, current_block)
        return new_index_c, new_index_o

    @staticmethod
    def remove_noise(lines, noise_limit):
        """
        Remove noise from the dot plot

        :param lines: lines of the dot plot, by class
        :type lines: dict
        :param noise_limit: line length limit
        :type noise_limit: float
        :return: kept lines, by class
        :rtype: dict
        """
        keep_lines = {
            "0": [],
            "1": [],
            "2": [],
            "3": []
        }
        for cls, c_lines in lines.items():
            for line in c_lines:
                x1 = line[0]
                x2 = line[1]
                y1 = line[2]
                y2 = line[3]
                idy = line[4]
                len_m = sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2))
                if len_m >= noise_limit:
                    keep_lines[cls].append(line)
        return keep_lines

    def keyerror_message(self, exception, type_f):
        """
        Build message if contig not found in query or target

        :param exception: exception object
        :type exception: KeyError
        :param type_f: type of data (query or target)
        :type type_f: str
        :return: error message
        :rtype: str
        """
        message = "Invalid contig for %s: %s" % (type_f, exception.args[0])
        if os.path.exists(os.path.join(self.data_dir, ".align")):
            message += ". May be you invert query and target files?"
        return message

    def parse_paf(self, merge_index=True, noise=True):
        """
        Parse PAF file

        :param merge_index: if True, merge too small contigs in index
        :type merge_index: bool
        :param noise: if True, remove noise
        :type noise: bool
        """
        min_idy = 10000000000
        max_idy = -10000000000
        lines = {
            "0": [],  # idy < 0.25
            "1": [],  # idy < 0.5
            "2": [],  # idy < 0.75
            "3": []  # idy > 0.75
        }
        try:
            name_q, q_order, q_contigs, q_reversed, q_abs_start, len_q = Index.load(self.idx_q)
            self.q_abs_start = q_abs_start
            if merge_index:
                q_contigs, q_order = self.parse_index(q_order, q_contigs, len_q)
        except IOError:
            self.error = "Index file does not exist for query!"
            return False

        try:
            name_t, t_order, t_contigs, t_reversed, t_abs_start, len_t = Index.load(self.idx_t)
            self.t_abs_start = t_abs_start
            if merge_index:
                t_contigs, t_order = self.parse_index(t_order, t_contigs, len_t)
        except IOError:
            self.error = "Index file does not exist for target!"
            return False

        lines_lens = []

        try:
            with open(self.paf, "r") as paf_file:
                nb_lines = 0
                for line in paf_file:
                    nb_lines += 1
                    if nb_lines > self.max_nb_lines:
                        self.sampled = True
                        break
                    parts = line.strip("\n").split("\t")
                    v1 = parts[0]
                    v6 = parts[5]
                    strand = 1 if parts[4] == "+" else -1
                    idy = int(parts[9]) / int(parts[10])
                    min_idy = min(min_idy, idy)
                    max_idy = max(max_idy, idy)
                    # x1, x2, y1, y2, idy
                    try:
                        y1 = int(parts[2]) + q_abs_start[v1]
                        y2 = int(parts[3]) + q_abs_start[v1]
                    except KeyError as e:
                        self.error = self.keyerror_message(e, "query")
                        return False
                    try:
                        x1 = int(parts[7 if strand == 1 else 8]) + t_abs_start[v6]
                        x2 = int(parts[8 if strand == 1 else 7]) + t_abs_start[v6]
                    except KeyError as e:
                        self.error = self.keyerror_message(e, "target")
                        return False
                    len_m = sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2))
                    lines_lens.append(len_m)
                    if idy < self.limit_idy[0]:
                        class_idy = "0"
                    elif idy < self.limit_idy[1]:
                        class_idy = "1"
                    elif idy < self.limit_idy[2]:
                        class_idy = "2"
                    else:
                        class_idy = "3"
                    lines[class_idy].append([x1, x2, y1, y2, idy, v1, v6])
        except IOError:
            self.error = "PAF file does not exist!"
            return False

        if not noise and nb_lines > 1000:
            counts, bins, bars = plt.hist(lines_lens, bins=nb_lines//10)
            counts = list(counts)
            max_value = max(counts)
            max_index = counts.index(max_value)
            limit_index = -1
            for i in range(max_index, len(counts)):
                if counts[i] < max_value / 50:
                    limit_index = i
                    break
            if limit_index > -1:
                lines = self.remove_noise(lines, bins[limit_index])

        self.parsed = True
        self.len_q = len_q
        self.len_t = len_t
        self.min_idy = min_idy
        self.max_idy = max_idy
        self.lines = lines
        self.q_contigs = q_contigs
        self.q_order = q_order
        self.q_reversed = q_reversed
        self.t_contigs = t_contigs
        self.t_order = t_order
        self.name_q = name_q
        self.name_t = name_t

    def get_d3js_data(self):
        """
        Build data for D3.js client

        :return: data for d3.js:

            * y_len: length of query (Bp)
            * x_len: length of target (Bp)
            * min_idy: minimum of identity (float)
            * max_idy: maximum of identity (float)
            * lines: matches lines, by class of identity (dict)
            * y_contigs: query contigs definitions (dict)
            * y_order: query contigs order (list)
            * x_contigs: target contigs definitions (dict)
            * x_order: target contigs order (list)
            * name_y: name of the query (str)
            * name_x: name of the target (str)
            * limit_idy: limit for each class of identities (list)
        :rtype: dict
        """
        return {
            'y_len': self.len_q,
            'x_len': self.len_t,
            'min_idy': self.min_idy,
            'max_idy': self.max_idy,
            'lines': self.lines,
            'y_contigs': self.q_contigs,
            'y_order': self.q_order,
            'x_contigs': self.t_contigs,
            'x_order': self.t_order,
            'name_y': self.name_q,
            'name_x': self.name_t,
            'limit_idy': self.limit_idy,
            'sorted': self.sorted,
            'sampled': self.sampled,
            "max_nb_lines": self.max_nb_lines,
        }

    def save_json(self, out):
        """
        Save D3.js data to json

        :param out: output file path
        :type out: str
        """
        import json
        data = self.get_d3js_data()
        with open(out, "w") as out_f:
            out_f.write(json.dumps(data))

    def is_contig_well_oriented(self, lines, contig, chrom):
        """
        Returns True if the contig is well oriented. A well oriented contig
        must have y increased when x increased. We check that only for highest matches
        (small matches must be ignored)

        :param lines: lines inside the contig
        :type lines: list
        :param contig: query contig name
        :type contig: str
        :param chrom: target chromosome name
        :type chrom: str
        :return: True if well oriented, False else
        :rtype: bool
        """
        lines.sort(key=lambda x: -x[-1])
        max_len = lines[0][-1]
        i = 0

        # Select samples of tested lines such that:
        # - a selected line is at least 10% of the longest line
        # - and a selected line is at least 1% of the length of contig or the length of chrom
        while i < len(lines) and lines[i][-1] > max_len * 0.1 \
                and lines[i][-1] >= 0.01 * min(self.q_contigs[contig], self.t_contigs[chrom]):
            i += 1
        selected_lines = lines[:i]

        # Check orientation of each line:
        if len(selected_lines) > 1:
            selected_lines.sort(key=lambda x: x[0])
            orients = []
            for i in range(1, len(selected_lines)):
                if selected_lines[i][2] > selected_lines[i-1][2]:
                    orients.append(1)
                else:
                    orients.append(-1)
            if mean(orients) > -0.1:  # We have a good orientation (-0.1 to ignore ambiguous cases)
                return True
        elif len(selected_lines) == 1:
            orient_first = "+" if selected_lines[0][3] < selected_lines[0][4] else "-"  # Get X orientation
            if selected_lines[0][-2 if orient_first == "+" else -3] > \
                    selected_lines[0][-3 if orient_first == "+" else -2]:  # Check Y according to X orientation
                return True
        elif len(selected_lines) == 0:  # None line were selected: we ignore this block
            return True

        # In all other cases the orientation is wrong:
        return False

    def reorient_contigs_in_paf(self, contigs):
        """
        Reorient contigs in the PAF file

        :param contigs: contigs to be reoriented
        """
        sorted_file = self.paf + ".sorted"
        contigs = set(contigs)
        with open(self.paf, "r") as source, open(sorted_file, "w") as target:
            for line in source:
                parts = line.strip("\n").split("\t")
                if parts[0] in contigs:
                    len_q = int(parts[1])
                    x1_q = int(parts[2])
                    x2_q = int(parts[3])
                    if parts[4] == "-":
                        parts[4] = "+"
                    else:
                        parts[4] = "-"
                    parts[2] = str(len_q - x2_q)
                    parts[3] = str(len_q - x1_q)
                target.write("\t".join(parts) + "\n")
        if self.paf.endswith(".sorted"):
            os.remove(self.paf)
            shutil.move(sorted_file, self.paf)
        else:
            self.paf = sorted_file
        return True

    def _update_query_index(self, contigs_reoriented):
        """
        Write new query index file (including new reoriented contigs info)

        :param contigs_reoriented: reoriented contigs list
        :type contigs_reoriented: list
        """
        contigs_reoriented = set(contigs_reoriented)
        with open(self.idx_q, "w") as idx:
            idx.write(self.name_q + "\n")
            for contig in self.q_order:
                idx.write("\t".join([contig, str(self.q_contigs[contig]), "1" if contig in contigs_reoriented else "0"])
                          + "\n")

    def set_sorted(self, is_sorted):
        """
        Change sorted status

        :param is_sorted: new sorted status
        :type is_sorted: bool
        """
        self.sorted = is_sorted
        sorted_touch = os.path.join(os.path.dirname(self.paf), ".sorted")
        if is_sorted:
            Path(sorted_touch).touch()
        else:
            if os.path.exists(sorted_touch):
                os.remove(sorted_touch)

    def compute_gravity_contigs(self):
        """
        Compute gravity for each contig on each chromosome (how many big matches they have).
        Will be used to find which chromosome has the highest value for each contig

        :return:

            * [0] gravity for each contig and each chromosome:
                {contig1: {chr1: value, chr2: value, ...}, contig2: ...}
            * [1] For each block save lines inside:
                [median_on_query, squared length, median_on_target, x1, x2, y1, y2, length] (x : on target, y: on query)
        """
        gravity_contig = {}
        lines_on_block = {}
        # Compute size of blocks (in term of how many big match they have), and save median of each match on each one
        # (for next step)
        for line in [j for i in list(self.lines.values()) for j in i]:
            x1 = int(line[0])
            x2 = int(line[1])
            y1 = int(line[2])
            y2 = int(line[3])
            contig = line[5]
            chrm = line[6]
            block = (contig, chrm)
            # X1 and X2 (in good orientation):
            x_1 = min(x1, x2)
            x_2 = max(x2, x1)
            med_q = x_1 + (abs(x_2 - x_1) / 2)
            # Y1 and Y2 (in good orientation):
            y_1 = min(y1, y2)
            y_2 = max(y2, y1)
            med_t = y_1 + (abs(y_2 - y_1) / 2)
            len_m = sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2))  # Len
            len_m_2 = pow(1 + len_m, 2) # Pow of len
            if block not in lines_on_block:
                lines_on_block[block] = []
            lines_on_block[block].append((med_q, len_m_2, med_t, x1, x2, y1, y2, len_m))

            if contig not in gravity_contig:
                gravity_contig[contig] = {}
            if chrm not in gravity_contig[contig]:
                gravity_contig[contig][chrm] = 0
            gravity_contig[contig][chrm] += len_m_2
        return gravity_contig, lines_on_block

    def sort(self):
        """
        Sort contigs according to reference target and reorient them if needed
        """
        self.parse_paf(False)
        sorted_file = self.paf + ".sorted"
        if not self.sorted:  # Do the sort
            if not self.paf.endswith(".sorted") and not self.idx_q.endswith(".sorted") and \
                    (not os.path.exists(self.paf + ".sorted") or not os.path.exists(self.idx_q + ".sorted")):
                gravity_contig , lines_on_block = self.compute_gravity_contigs()

                # For each contig, find best block, and deduce gravity of contig:
                gravity_on_contig = {}
                reorient_contigs = []
                for contig, chr_blocks in gravity_contig.items():
                    # Find best block:
                    max_number = 0
                    max_chr = None
                    for chrm, size in chr_blocks.items():
                        if size > max_number:
                            max_number = size
                            max_chr = chrm

                    # Compute gravity of contig:
                    nb_items = 0
                    sum_items = 0
                    lines_on_selected_block = lines_on_block[(contig, max_chr)]
                    for med in lines_on_selected_block:
                        sum_items += med[0] * med[1]
                        nb_items += med[1]
                    gravity_on_contig[contig] = sum_items / nb_items

                    # Check if contig must be re-oriented:
                    if len(lines_on_selected_block) > 0:
                        if not self.is_contig_well_oriented(lines_on_selected_block, contig, max_chr):
                            reorient_contigs.append(contig)

                # Sort contigs:
                self.q_order.sort(key=lambda x: gravity_on_contig[x] if x in gravity_on_contig else self.len_q + 1000)

                self.idx_q += ".sorted"

                with open(self.idx_q, "w") as idx_q_f:
                    idx_q_f.write(self.name_q + "\n")
                    for contig in self.q_order:
                        idx_q_f.write("\t".join([contig, str(self.q_contigs[contig])]) + "\n")

                # Re-orient contigs:
                if len(reorient_contigs) > 0:
                    self.reorient_contigs_in_paf(reorient_contigs)
                else:
                    shutil.copyfile(self.paf, sorted_file)

                # Update index:
                self._update_query_index(reorient_contigs)

            else:
                self.idx_q += ".sorted"
            self.set_sorted(True)
            self.paf = sorted_file

        else:  # Undo the sort
            self.paf = self.paf.replace(".sorted", "")
            self.idx_q = self.idx_q.replace(".sorted", "")
            self.set_sorted(False)

        # Re parse PAF file:
        self.parsed = False
        self.parse_paf()

    def reverse_contig(self, contig_name):
        """
        Reverse contig

        :param contig_name: contig name
        :type contig_name: str
        """
        self.parse_paf(False)
        reorient_contigs = [contig_name]
        self.reorient_contigs_in_paf(reorient_contigs)
        if not self.idx_q.endswith(".sorted"):
            self.idx_q += ".sorted"
        self._update_query_index(reorient_contigs)
        self.set_sorted(True)
        self.parsed = False
        self.parse_paf()

    def get_query_on_target_association(self, with_coords=True):
        """
        For each query, get the best matching chromosome

        :return: query on target association
        :rtype: dict
        """
        gravity_contig, lines_on_block = self.compute_gravity_contigs()
        query_on_target = {}
        for contig, chr_blocks in gravity_contig.items():
            # Find best block:
            max_number = 0
            max_chr = None
            min_target = -1
            max_target = -1
            min_query = -1
            max_query = -1
            for chrm, size in chr_blocks.items():
                if size > max_number:
                    max_number = size
                    max_chr = chrm
                    min_target = -1
                    max_target = -1
                    min_query = -1
                    max_query = -1
                    if with_coords:
                        for line in lines_on_block[(contig, chrm)]:
                            x1 = min(line[3], line[4]) - self.t_abs_start[chrm]
                            x2 = max(line[3], line[4]) - self.t_abs_start[chrm]
                            if x1 < min_target or min_target == -1:
                                min_target = x1
                            if x2 > max_target:
                                max_target = x2
                            y1 = min(line[5], line[6]) - self.q_abs_start[contig]
                            y2 = max(line[5], line[6]) - self.q_abs_start[contig]
                            if y1 < min_query or min_query == -1:
                                min_query = y1
                            if y2 > max_query:
                                max_query = y2
            if max_chr is not None:
                query_on_target[contig] = (max_chr, min_query, max_query, min_target, max_target)
            else:
                query_on_target[contig] = None
        return query_on_target

    def get_queries_on_target_association(self):
        """
        For each target, get the list of queries associated to it

        :return: list of queries associated to each target
        :rtype: dict
        """
        gravity_contig = self.compute_gravity_contigs()[0]
        queries_on_target = {}
        for contig, chr_blocks in gravity_contig.items():
            # Find best block:
            max_number = 0
            max_chr = None
            for chrm, size in chr_blocks.items():
                if size > max_number:
                    max_number = size
                    max_chr = chrm
            if max_chr is not None:
                if max_chr not in queries_on_target:
                    queries_on_target[max_chr] = []
                queries_on_target[max_chr].append(contig)
        return queries_on_target

    def build_query_on_target_association_file(self):
        """
        For each query, get the best matching chromosome and save it to a CSV file.
        Use the order of queries

        :return: content of the file
        """
        query_on_target = self.get_query_on_target_association(with_coords=True)
        content = "Query\tTarget\tStrand\tQ-len\tQ-start\tQ-stop\tT-len\tT-start\tT-stop\n"
        for contig in self.q_order:
            strand = "+"
            if contig in self.q_reversed:
                strand = "-" if self.q_reversed[contig] else "+"
            if contig in query_on_target:
                min_target = str(query_on_target[contig][3])
                if min_target == "-1":
                    min_target = "na"
                max_target = str(query_on_target[contig][4])
                if max_target == "-1":
                    max_target = "na"
                min_query = str(query_on_target[contig][1])
                if min_query == "-1":
                    min_query = "na"
                max_query = str(query_on_target[contig][2])
                if max_query == "-1":
                    max_query = "na"
                chrm = query_on_target[contig][0]
                content += "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (contig, chrm or "None", strand,
                                                                     str(self.q_contigs[contig]), min_query, max_query,
                                                                     str(self.t_contigs[chrm]), min_target, max_target)
            else:
                content += "%s\t%s\t%s\t%s\tna\tna\tna\tna\tna\n" % (contig, "None", strand,
                                                                     str(self.q_contigs[contig]))
        return content

    def build_list_no_assoc(self, to):
        """
        Build list of queries that match with None target, or the opposite

        :param to: query or target
        :return: content of the file
        """
        index = self.idx_q if to == "query" else self.idx_t
        name, contigs_list, contigs, reversed, abs_start, c_len = Index.load(index)
        contigs_list = set(contigs_list)
        with open(self.paf, "r") as paf:
            for line in paf:
                c_name = line.strip("\n").split("\t")[0 if to == "query" else 5]
                if c_name in contigs_list:
                    contigs_list.remove(c_name)
        return "\n".join(contigs_list) + "\n"

    def _add_percents(self, percents, item):
        """
        Update percents with interval

        :param percents: initial percents
        :type percents: dict
        :param item: interval from IntervalTree
        :type item: Interval
        :return: new percents
        :rtype: dict
        """
        i_count = item.length()
        percents[str(item.data)] += i_count
        percents["-1"] -= i_count
        return percents

    def _remove_overlaps(self, position_idy, percents):
        """
        Remove overlaps between matches on the diagonal

        :param position_idy: matches intervals with associated identity category
        :type position_idy: IntervalTree
        :param percents: Percent of matches for each identity category
        :type percents: dict
        :return: new percents (updated after overlap removing)
        :rtype: dict
        """
        while len(position_idy) > 0:
            item = position_idy.pop()
            start = item.begin
            end = item.end
            cat = item.data
            overlaps = position_idy.overlap(start, end)
            if len(overlaps) > 0:
                has_overlap = False
                for overlap in overlaps:
                    if has_overlap:
                        break
                    o_start = overlap.begin
                    o_end = overlap.end
                    o_cat = overlap.data
                    if not position_idy.containsi(o_start, o_end, o_cat):
                        continue
                    if start < o_start:
                        if end <= o_end:
                            # cccccccccccccc*******
                            # *****ooooooooo[ooooooo]
                            if o_cat < cat:
                                if end < o_end:
                                    # No overlap with the current item, we stay has_overlap as False
                                    position_idy.discard(overlap)
                                    position_idy[end:o_end] = o_cat
                                else:
                                    position_idy.discard(overlap)  # No kept overlap
                            elif o_cat == cat:
                                if end < o_end:
                                    has_overlap = True
                                    position_idy.discard(overlap)
                                    position_idy[start:o_end] = cat
                                else:
                                    position_idy.discard(overlap)  # No kept overlap
                            else:
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[start:o_start] = cat
                                position_idy[o_start:o_end] = o_cat
                        else:  # end > o_end
                            # ccccccccccccccccccc
                            # *****oooooooooo****
                            if o_cat <= cat:
                                position_idy.discard(overlap)  # No kept overlap
                            else:  # o_cat > cat
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[start:o_start] = cat
                                position_idy[o_start:o_end] = o_cat
                                position_idy[o_end:end] = cat
                    elif start == o_start:
                        if end < o_end:
                            # cccccccccccc*******
                            # ooooooooooooooooooo
                            if o_cat < cat:
                                # No overlap with the current item, we stay has_overlap as False
                                position_idy.discard(overlap)
                                position_idy[end:o_end] = o_cat
                            elif o_cat == cat:
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[start:o_end] = cat
                            else:  # o_cat > cat
                                # The overlap just contains current item
                                has_overlap = True
                        elif end == o_end:
                            # ***cccccccccccccccc***
                            # ***oooooooooooooooo***
                            if o_cat <= cat:
                                position_idy.discard(overlap)  # No kept overlap
                            else:
                                # The overlap just contains current item
                                has_overlap = True
                        else:  # end > o_end
                            # ccccccccccccccccccccccccccccc
                            # oooooooooooooooooooo*********
                            if o_cat <= cat:
                                # current item just contains the overlap
                                position_idy.discard(overlap)
                            else:
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[o_start:o_end] = o_cat
                                position_idy[o_end:end] = cat
                    else:  # start > o_start
                        if end <= o_end:
                            # ******ccccccccc*******
                            # ooooooooooooooo[ooooooo]
                            if o_cat < cat:
                                has_overlap=True
                                position_idy.discard(overlap)
                                position_idy[o_start:start] = o_cat
                                position_idy[start:end] = cat
                                if end < o_end:
                                    position_idy[end:o_end] = o_cat
                            else:  # o_cat >= cat
                                # Overlap just contains the item
                                has_overlap = True
                        else: # end > o_end
                            # ******ccccccccccccccccccccc
                            # ooooooooooooooooo**********
                            if o_cat < cat:
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[o_start:start] = o_cat
                                position_idy[start:end] = cat
                            elif o_cat == cat:
                                has_overlap = True
                                position_idy.discard(overlap)
                                position_idy[o_start:end] = cat
                            else:  # o_cat > cat
                                has_overlap = True
                                position_idy[o_end:end] = cat
                if not has_overlap:
                    percents = self._add_percents(percents, item)

            else:
                percents = self._add_percents(percents, item)

        return percents

    def build_summary_stats(self, status_file):
        """
        Get summary of identity

        :return: table with percents by category
        """
        summary_file = self.paf + ".summary"
        self.parse_paf(False, False)
        if self.parsed:
            percents = {"-1": self.len_t}
            position_idy = IntervalTree()

            cats = sorted(self.lines.keys())

            for cat in cats:
                percents[cat] = 0
                for line in self.lines[cat]:
                    start = min(line[0], line[1])
                    end = max(line[0], line[1]) + 1
                    position_idy[start:end] = int(cat)

            percents = self._remove_overlaps(position_idy, percents)

            for cat in percents:
                percents[cat] = percents[cat] / self.len_t * 100

            with open(summary_file, "w") as summary_file:
                summary_file.write(json.dumps(percents))

            os.remove(status_file)
            return percents
        shutil.move(status_file, status_file + ".fail")
        return None

    def get_summary_stats(self):
        """
        Load summary statistics from file

        :return: summary object or None if summary not already built
        :rtype: dict
        """
        summary_file = self.paf + ".summary"
        if os.path.exists(summary_file):
            with open(summary_file, "r") as summary_file:
                txt = summary_file.read()
                return json.loads(txt)
        return None

    def build_query_chr_as_reference(self):
        """
        Assemble query contigs like reference chromosomes

        :return: path of the fasta file
        """
        try:
            if not self.sorted:
                raise Exception("Contigs must be sorted to do that!")
            with open(os.path.join(self.data_dir, ".query")) as query_file:
                query_fasta = query_file.read().strip("\n")
            if not os.path.isfile(query_fasta):
                raise Exception("Query fasta does not exists")
            o_fasta = os.path.join(os.path.dirname(query_fasta), "as_reference_" + os.path.basename(query_fasta))
            if o_fasta.endswith(".gz"):
                o_fasta = o_fasta[:-3]
            if not os.path.exists(o_fasta):
                uncompressed = False
                if query_fasta.endswith(".gz"):
                    uncompressed = True
                    query_fasta = Functions.uncompress(query_fasta)
                query_f = SeqIO.index(query_fasta, "fasta")
                contigs_assoc = self.get_queries_on_target_association()
                mapped_queries = set()
                with open(o_fasta, "w") as out:
                    for target in self.t_order:
                        if target in contigs_assoc:
                            queries = sorted(contigs_assoc[target], key=lambda x: self.q_order.index(x))
                            seq = SeqRecord(Seq(""))
                            for query in queries:
                                mapped_queries.add(query)
                                new_seq = query_f[query]
                                if self.q_reversed[query]:
                                    new_seq = new_seq.reverse_complement()
                                seq += new_seq
                                seq += 100 * "N"
                            seq = seq[:-100]
                            seq.id = seq.name = seq.description = target
                            SeqIO.write(seq, out, "fasta")
                    for contig in self.q_order:
                        if contig not in mapped_queries:
                            seq = query_f[contig]
                            seq.id += "_unaligned"
                            SeqIO.write(seq, out, "fasta")
                query_f.close()
                if uncompressed:
                    os.remove(query_fasta)
            status = "success"
        except Exception:
            o_fasta = "_._"
            status="fail"

        if MODE == "webserver":
            parts = os.path.basename(o_fasta).rsplit(".", 1)
            Functions.send_fasta_ready(mailer=self.mailer,
                                       job_name=self.id_job,
                                       sample_name=parts[0],
                                       ext=parts[1],
                                       compressed=False,
                                       path="download",
                                       status=status)
        return o_fasta
