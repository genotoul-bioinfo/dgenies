# Description of file formats used in D-Genies

##PAF (Pairwise mApping Format)

Default output format of minimap2.

It's a tabulated file. Description of columns below.

Col | Type   | Description                               
--- | ------ | -----------------------------------------
1   | string | Query sequence name                       
2   | int    | Query sequence length                     
3   | int    | Query start coordinate (0-based)                     
4   | int    | Query end coordinate (0-based)                       
5   | char   | ‘+’ if query/target on the same strand; ‘-’ if opposite               
6   | string | Target sequence name                      
7   | int    | Target sequence length                    
8   | int    | Target start on original strand (0-based) 
9   | int    | Target end on original strand (0-based)   
10  | int    | Number of matching bases in the mapping                 
11  | int    | Number bases, including gaps, in the mapping                    
12  | int    | Mapping quality (0-255; 255 for missing)  

Column 11 gives the total number of sequence matches, mismatches and gaps in the alignment; column 10 divided by column 11 gives the BLAST-like alignment identity.

PAF may optionally have additional fields in the SAM-like typed key-value format. Minimap2 may output the following tags:
 
Tag | Type | Description
--- | ---- | -----------------------------------------
tp  | A	   | Type of aln: P/primary, S/secondary and I,i/inversion
cm	| i    | Number of minimizers on the chain
s1	| i	   | Chaining score
s2	| i	   | Chaining score of the best secondary chain
NM	| i	   | Total number of mismatches and gaps in the alignment
AS	| i	   | DP alignment score
ms	| i	   | DP score of the max scoring segment in the alignment
nn	| i	   | Number of ambiguous bases in the alignment

Source: [minimap2 documentation](https://lh3.github.io/minimap2/minimap2.html).


## Maf (Multiple Alignment File)

Description of the format is available [here](http://www.bx.psu.edu/~dcking/man/maf.xhtml).

## Index file

Index files used in D-Genies are built as follow.

First line contains the name of the sample. Next lines describes contigs of the sample. They are composed of two columns, tab separated. First it the name of the contig, second it's size in bases.

Example:

    Homo sapiens  
    chr1    248956422  
    chr2    242193529  
    chr3    198295559

## Backup file

Backup file is a TAR archive. It contains three files:

* The alignment file, in paf format, named `map.paf`.
* The target index, named `target.idx`.
* The query index, named `query.idx`.

Names of files must be kept. Otherwise, the backup file will not be accepted by the run form.