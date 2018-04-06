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
                paf.write("{qname}\t{qlen}\t{qstart}\t{qend}\t{strand}\t{tname}\t{tlen}\t{tstart}\t{tend}\t{matches}\t"
                          "{block_len}\t255\n".format(
                            tname=seqs[0].id,
                            tlen=tannots["srcSize"],
                            tstart=tannots["start"],
                            tend=tannots["start"] + tannots["size"],
                            qname=seqs[1].id,
                            qlen=qannots["srcSize"],
                            qstart=qannots["start"],
                            qend=qannots["start"] + qannots["size"],
                            strand="+" if tannots["strand"] == qannots["strand"] else "-",
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
