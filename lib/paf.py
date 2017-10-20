#!/usr/bin/env python3


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
        self.lines = None
        self.q_contigs = None
        self.q_order = None
        self.t_contigs = None
        self.t_order = None
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
                    lines[class_idy].append([x1, x2, y1, y2, idy])
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
