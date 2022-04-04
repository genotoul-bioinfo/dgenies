Definitions
-----------

### Identity

The identity value $I$ is a BLAST-like alignment identity computed from the [PAF file](/documentation/formats#paf-pairwise-mapping-format) such as:

$$I=\frac{M}{N}$$

where $M$ is the *Number of matching bases in the mapping* and $N$ is the *Number bases, including gaps, in the mapping*.

### Best matching chromosome

This *best matching chromosome* section is about the association of each contig in $\mathrm{Query}$  to a chromosome in $\mathrm{Target}$.
Please note that this definition is extracted from source code and may be inexact, as the original author didn't document this part.

Let $L$ denote the set of alignments between $\mathrm{Query}$ and $\mathrm{Target}$ (i.e. lines in the dotplot), $q$ a contig from $\mathrm{Query}$, and $t$ a chromosome from $\mathrm{Target}$.

We define $L(q,t) \subseteq L$ the set of alignments between $q$ and $t$, and $\mathrm{gravity}$ a score function such as:

$$
\mathrm{gravity}(q,t) = \sum_{l \in L(q,t)} (1 + ||l||)^2
$$

where $ ||l|| = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2} $ with:

* $(x_1, x_2)$ the coordinates of $l$ on $t$, and
* $(y_1, y_2)$ the coordinates of $l$ on $q$.


For a given contig $q \in \mathrm{Query}$, the best matching chromosome $\tau \in \mathrm{Target}$ is the chromosome that maximize the $\mathrm{gravity}$ function, i.e. $\tau$ is defined such as:

$$
\mathrm{gravity}(q, \tau) = \max_{\forall t \in \mathrm{Target}} \mathrm{gravity}(q, t)
$$
