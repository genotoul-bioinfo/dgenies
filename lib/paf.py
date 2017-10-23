#!/usr/bin/env python3

from math import sqrt


class Paf:
    limit_idy = 0.5

    def __init__(self, paf, idx_q, idx_t):
        self.paf = paf
        self.idx_q = idx_q
        self.idx_t = idx_t

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
                for line in paf_file:
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
            'limit_idy': self.limit_idy
        }

    def save_json(self, out):
        import json
        success, data = self.parse_paf()
        if success:
            with open(out, "w") as out_f:
                out_f.write(json.dumps(data))
        else:
            raise Exception(data)

    def sort(self):
        gravity_contig = {}
        lines_on_block = {}
        # Compute size of blocks (in term of how many big match they have), and save median of each match on each one
        # (for next step)
        for line in [j for i in list(self.lines.values()) for j in i]:
            x1 = int(line[0])
            x2 = int(line[1])
            y1 = int(line[2])
            y2 = int(line[3])
            idy = int(line[4])
            contig = line[5]
            chrm = line[6]
            block = (contig, chrm)
            med_q = x1 + (abs(x2 - x1) / 2)
            len_m = sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2))  # Pow of len
            len_m_2 = pow(1 + len_m, 2)
            if block not in lines_on_block:
                lines_on_block[block] = []
            lines_on_block[block].append((med_q, len_m_2))

            if contig not in gravity_contig:
                gravity_contig[contig] = {}
            if chrm not in gravity_contig[contig]:
                gravity_contig[contig][chrm] = 0
            gravity_contig[contig][chrm] += len_m_2

        # For each contig, find best block, and deduce gravity of contig:
        gravity_on_contig = {}
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
            for med in lines_on_block[(contig, max_chr)]:
                sum_items += med[0] * med[1]
                nb_items += med[1]
            gravity_on_contig[contig] = sum_items / nb_items

        # Sort contigs:
        self.q_order.sort(key=lambda x: gravity_on_contig[x] if x in gravity_on_contig else self.len_q + 1000)

        with open(self.idx_q, "w") as idx_q_f:
            idx_q_f.write(self.name_q + "\n")
            for contig in self.q_order:
                idx_q_f.write("\t".join([contig, str(self.q_contigs[contig])]) + "\n")
        self.parsed = False
        self.parse_paf()
