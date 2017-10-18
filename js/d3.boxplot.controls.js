if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.controls = {};

d3.boxplot.controls.init = function () {
    $("#sort-contigs").click(d3.boxplot.controls.launch_sort_contigs)
};

d3.boxplot.controls.launch_sort_contigs = function () {
    alert("Not supported yet!");
    $.post(`/sort/${d3.boxplot.id_res}`,
        {},
        function (data) {
            console.log(data);
        }
    );
};