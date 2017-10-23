if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.controls = {};

d3.boxplot.controls.init = function () {
    $("#sort-contigs").click(d3.boxplot.controls.launch_sort_contigs)
};

d3.boxplot.controls.launch_sort_contigs = function () {
    $("#loading").find(".mylabel").html("Building...");
    $("#loading").show();
    window.setTimeout(() => {
            $.post(`/sort/${d3.boxplot.id_res}`,
                {},
                function (data) {
                    if (data["success"]) {
                        $("#loading").find(".mylabel").html("Loading...");
                        window.setTimeout(() => {
                            d3.boxplot.launch(data, true);
                        }, 0);
                    }
                    else {
                        $("#loading").find(".mylabel").html("Loading...");
                        $("#loading").hide();
                        alert("An error occurred!");
                    }
                }
            );
        }, 0);
};