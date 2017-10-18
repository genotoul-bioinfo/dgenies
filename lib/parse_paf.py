#!/usr/bin/env python3
limit_idy = 0.5


def parse_paf(paf, idx1, idx2):
    len_x = 0
    len_y = 0
    min_idy = 10000000000
    max_idy = -10000000000
    first_sample = None
    second_sample = None
    lines = {
        "pos+": [],
        "pos-": [],
        "neg+": [],
        "neg-": []
    }
    try:
        with open(paf, "r") as paf_file:
            for line in paf_file:
                parts = line.strip("\n").split("\t")
                v1 = parts[0]
                v6 = parts[5]
                ignore = False
                strand = 1 if parts[4] == "+" else -1
                idy = int(parts[9]) / int(parts[10]) * strand
                min_idy = min(min_idy, idy)
                max_idy = max(max_idy, idy)
                if first_sample is None:
                    first_sample = v1
                elif first_sample != v1:
                    ignore = True
                if not ignore:
                    second_sample = v6
                    len_x = int(parts[1])
                    len_y = int(parts[6])
                    # x1, x2, y1, y2, idy
                    x1 = int(parts[2])
                    x2 = int(parts[3])
                    y1 = int(parts[7 if strand == 1 else 8])
                    y2 = int(parts[8 if strand == 1 else 7])
                    if idy < -limit_idy:
                        class_idy = "neg-"
                    elif idy < 0:
                        class_idy = "neg+"
                    elif idy < limit_idy:
                        class_idy = "pos-"
                    else:
                        class_idy = "pos+"
                    lines[class_idy].append([x1, x2, y1, y2, idy])
    except IOError:
        return False, "PAF file does not exist!"

    try:
        with open(idx1, "r") as idx1_f:
            x_order = []
            x_contigs = {}
            for line in idx1_f:
                parts = line.strip("\n").split("\t")
                id_c = parts[0]
                len_c = int(parts[1])
                x_order.append(id_c)
                x_contigs[id_c] = len_c
    except IOError:
        return False, "Index file does not exist for sample 1!"

    try:
        with open(idx2, "r") as idx2_f:
            y_order = []
            y_contigs = {}
            for line in idx2_f:
                parts = line.strip("\n").split("\t")
                id_c = parts[0]
                len_c = int(parts[1])
                y_order.append(id_c)
                y_contigs[id_c] = len_c
    except IOError:
        return False, "Index file does not exist for sample 2!"

    return True, {
        'x_len': len_x,
        'y_len': len_y,
        'min_idy': min_idy,
        'max_idy': max_idy,
        'lines': lines,
        'x_contigs': x_contigs,
        'x_order': x_order,
        'y_contigs': y_contigs,
        'y_order': y_order,
        'name_x': first_sample,
        'name_y': second_sample,
        'limit_idy': limit_idy
    }


def save_json(paf, idx1, idx2, out):
    import json
    success, data = parse_paf(paf, idx1, idx2)
    if success:
        with open(out, "w") as out_f:
            out_f.write(json.dumps(data))
    else:
        raise Exception(data)
