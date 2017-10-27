#!/usr/bin/env python3

import os
from math import sqrt
from numpy import mean


class Paf:
    limit_idy = 0.5
    max_nb_lines = 100000

    def __init__(self, paf: str, idx_q: str, idx_t: str):
        self.paf = paf
        self.idx_q = idx_q
        self.idx_t = idx_t
        self.sorted = False
        if os.path.exists(paf + ".sorted") and os.path.exists(idx_q + ".sorted"):
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
        self.name_q = None
        self.name_t = None
        self.parsed = False
        self.error = False

        self.parse_paf()

    def parse_paf(self):
        len_q = 0
        len_t = 0
        min_idy = 10000000000
        max_idy = -10000000000
        name_q = None
        name_t = None
        lines = {
            "pos+": [],
            "pos-": [],
            "neg+": [],
            "neg-": []
        }
        q_abs_start = {}
        q_abs_current_start = 0
        try:
            with open(self.idx_q, "r") as idx_q_f:
                name_q = idx_q_f.readline().strip("\n")
                q_order = []
                q_contigs = {}
                for line in idx_q_f:
                    parts = line.strip("\n").split("\t")
                    id_c = parts[0]
                    len_c = int(parts[1])
                    q_order.append(id_c)
                    q_abs_start[id_c] = q_abs_current_start
                    q_contigs[id_c] = len_c
                    q_abs_current_start += len_c
        except IOError:
            self.error = "Index file does not exist for query!"
            return False

        t_abs_start = {}
        t_abs_current_start = 0
        try:
            with open(self.idx_t, "r") as idx_t_f:
                name_t = idx_t_f.readline().strip("\n")
                t_order = []
                t_contigs = {}
                for line in idx_t_f:
                    parts = line.strip("\n").split("\t")
                    id_c = parts[0]
                    len_c = int(parts[1])
                    t_order.append(id_c)
                    t_abs_start[id_c] = t_abs_current_start
                    t_contigs[id_c] = len_c
                    t_abs_current_start += len_c
        except IOError:
            self.error = "Index file does not exist for target!"
            return False

        len_q = q_abs_current_start
        len_t = t_abs_current_start

        try:
            with open(self.paf, "r") as paf_file:
                paf_lines = paf_file.readlines()
                if len(paf_lines) > self.max_nb_lines:
                    self.sampled = True
                for line in paf_lines[:self.max_nb_lines]:
                    parts = line.strip("\n").split("\t")
                    v1 = parts[0]
                    v6 = parts[5]
                    strand = 1 if parts[4] == "+" else -1
                    idy = int(parts[9]) / int(parts[10]) * strand
                    min_idy = min(min_idy, idy)
                    max_idy = max(max_idy, idy)
                    # x1, x2, y1, y2, idy
                    y1 = int(parts[2]) + q_abs_start[v1]
                    y2 = int(parts[3]) + q_abs_start[v1]
                    x1 = int(parts[7 if strand == 1 else 8]) + t_abs_start[v6]
                    x2 = int(parts[8 if strand == 1 else 7]) + t_abs_start[v6]
                    if idy < -self.limit_idy:
                        class_idy = "neg-"
                    elif idy < 0:
                        class_idy = "neg+"
                    elif idy < self.limit_idy:
                        class_idy = "pos-"
                    else:
                        class_idy = "pos+"
                    lines[class_idy].append([x1, x2, y1, y2, idy, v1, v6])
        except IOError:
            self.error = "PAF file does not exist!"
            return False

        self.parsed = True
        self.len_q = len_q
        self.len_t = len_t
        self.min_idy = min_idy
        self.max_idy = max_idy
        self.lines = lines
        self.q_contigs = q_contigs
        self.q_order = q_order
        self.t_contigs = t_contigs
        self.t_order = t_order
        self.name_q = name_q
        self.name_t = name_t

    def get_d3js_data(self):
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
        import json
        success, data = self.parse_paf()
        if success:
            with open(out, "w") as out_f:
                out_f.write(json.dumps(data))
        else:
            raise Exception(data)

    def is_contig_well_oriented(self, lines: list, contig, chrom):
        """
        Returns True if the contig is well oriented. A well oriented contig
        must have y increased when x increased. We check that only for highest matchs
        (small matches must be ignores)
        :param lines: lines inside the contig
        :return: True if well oriented, False else
        """
        lines.sort(key=lambda x: -x[-1])
        max_len = lines[0][-1]
        i = 0

        # Select sample of tested lines:
        while i < len(lines) and lines[i][-1] > max_len * 0.1 \
                and lines[i][-1] >= 0.05 * min(self.q_contigs[contig], self.t_contigs[chrom]):
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
        self.paf = sorted_file
        return True

    def _update_query_index(self, contigs_reoriented):
        with open(self.idx_q, "w") as idx:
            idx.write(self.name_q + "\n")
            for contig in self.q_order:
                idx.write("\t".join([contig, str(self.q_contigs[contig]), "1" if contig in contigs_reoriented else "0"])
                          + "\n")

    def sort(self):
        if not self.sorted:  # Do the sort
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
                len_m = sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2))  # Pow of len
                len_m_2 = pow(1 + len_m, 2)
                if block not in lines_on_block:
                    lines_on_block[block] = []
                lines_on_block[block].append((med_q, len_m_2, med_t, x1, x2, y1, y2, len_m))

                if contig not in gravity_contig:
                    gravity_contig[contig] = {}
                if chrm not in gravity_contig[contig]:
                    gravity_contig[contig][chrm] = 0
                gravity_contig[contig][chrm] += len_m_2

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

            # Update index:
            self._update_query_index(reorient_contigs)

            self.sorted = True

        else:  # Undo the sort
            if os.path.exists(self.paf):
                os.remove(self.paf)
                self.paf = self.paf.replace(".sorted", "")
            if os.path.exists(self.idx_q):
                os.remove(self.idx_q)
                self.idx_q = self.idx_q.replace(".sorted", "")
            self.sorted = False

        # Re parse PAF file:
        self.parsed = False
        self.parse_paf()
