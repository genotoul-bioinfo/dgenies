"""
Define tools parsers here

Each parser (main function) must have 2 and only 2 arguments:
- First argument: input file which is the tool raw output
- Second argument: finale PAF file
"""


def mashmap2paf(in_paf, out_paf):
    with open(in_paf, "r") as in_p, open(out_paf, "w") as out_p:
        for line in in_p:
            parts = line.rstrip().split(" ")
            parts[9] = str(round(float(parts[9]) / 100.0 * 1000.0))
            parts.append("1000")
            out_p.write("\t".join(parts) + "\n")
