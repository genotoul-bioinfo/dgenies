# Dot plot

In bioinformatics a dot plot is a graphical method that allows the comparison of two biological sequences and identify regions of close similarity between them. It is a type of recurrence plot.

More details of dot plot [here](https://en.wikipedia.org/wiki/Dot_plot_(bioinformatics)). Below, some examples of events which can be detected by dot plots.

## Match

When two samples sequence are identical, it's a match.

![match](/static/images/dotplot/match.png)

## Gap

Dot plots can be used to detect a gap between two samples: small sequence which exists only in one sample, between two matching regions.

![gap](/static/images/dotplot/gap.png)

## Inversion

Sequence which exists in the two samples but not in the same order.

![inversion](/static/images/dotplot/inversion.png)

## Repeats

Dot plot can be used to detect repeated regions: a sequence which is repeated several times in a sample.

![repeats](/static/images/dotplot/repeat2.png)