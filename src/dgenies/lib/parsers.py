"""
Define tools parsers here

Each parser (main function) must have 2 and only 2 arguments:
- First argument: input file which is the tool raw output
- Second argument: finale PAF file

Returns True if parse succeed, else False
"""

import traceback
from Bio import AlignIO


def maf(in_maf, out_paf):
    """
    Maf parser

    :param in_maf: input maf file path
    :type in_maf: str
    :param out_paf:  output paf file path
    :type out_paf: str
    :return: True if success, else False
    """
    maf_f = None
    try:
        with open(out_paf, "w") as paf:
            maf_f = AlignIO.parse(in_maf, "maf")
            for grp in maf_f:
                seqs = []
                for seq in grp:
                    seqs.append(seq)
                matches = 0
                for i in range(0, len(seqs[0])):
                    if seqs[0][i] == seqs[1][i]:
                        matches += 1
                tannots = seqs[0].annotations
                qannots = seqs[1].annotations
                tlen = tannots["srcSize"]
                tstart = tannots["start"]
                tend = tstart + tannots["size"]
                if tannots["strand"] == -1:
                    tstart = tlen - tstart
                    tend = tlen - tend
                qlen = qannots["srcSize"]
                qstart = qannots["start"]
                qend = qannots["start"] + qannots["size"]
                if qannots["strand"] == -1:
                    qstart = qlen - qstart
                    qend = qlen - qend
                strand = "+" if tannots["strand"] == qannots["strand"] else "-"
                paf.write("{qname}\t{qlen}\t{qstart}\t{qend}\t{strand}\t{tname}\t{tlen}\t{tstart}\t{tend}\t{matches}\t"
                          "{block_len}\t255\n".format(
                            tname=seqs[0].id,
                            tlen=tlen,
                            tstart=tstart,
                            tend=tend,
                            qname=seqs[1].id,
                            qlen=qlen,
                            qstart=qstart if strand == "+" else qend,
                            qend=qend if strand == "+" else qstart,
                            strand=strand,
                            matches=matches,
                            block_len=tannots["size"]
                          ))
    except:
        traceback.print_exc()
        if maf_f is not None:
            maf_f.close()
        return False
    else:
        maf_f.close()
        return True


def mashmap2paf(in_paf, out_paf):
    with open(in_paf, "r") as in_p, open(out_paf, "w") as out_p:
        for line in in_p:
            parts = line.rstrip().split(" ")
            parts[9] = str(round(float(parts[9]) / 100.0 * 1000.0))
            parts.append("1000")
            out_p.write("\t".join(parts) + "\t255" + "\n")

