if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.controls = {};

d3.boxplot.controls.init = function () {
    $("#sort-contigs").click(d3.boxplot.controls.launch_sort_contigs)
};

d3.boxplot.controls.launch_sort_contigs = function () {
    dgenies.set_loading_message("Building...");
    dgenies.show_loading();
    window.setTimeout(() => {
            $.post(`/sort/${d3.boxplot.id_res}`,
                {},
                function (data) {
                    if (data["success"]) {
                        dgenies.reset_loading_message();
                        window.setTimeout(() => {
                            d3.boxplot.launch(data, true);
                        }, 0);
                    }
                    else {
                        dgenies.hide_loading();
                        alert("An error occurred!");
                    }
                }
            );
        }, 0);
};