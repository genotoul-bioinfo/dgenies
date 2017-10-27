if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.controls = {};

d3.boxplot.controls.init = function () {
    $("#sort-contigs").click(d3.boxplot.controls.launch_sort_contigs);
    $("form#select-zone input.submit").click(d3.boxplot.controls.select_zone);
    $("form#export select").change(d3.boxplot.controls.export);
};

d3.boxplot.controls.launch_sort_contigs = function () {
    d3.boxplot.reset_scale();
    window.setTimeout(() => {
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
    }, 0);
};

d3.boxplot.controls.select_zone = function() {
    let contig_select = $("#select-contig").find(":selected");
    let target_select = $("#select-target").find(":selected");
    if (parseInt(contig_select.val()) > 0 && parseInt(target_select.val())) {
        d3.boxplot.select_zone(null, null, target_select.text(), contig_select.text(), true);
    }
    else {
        dgenies.notify("Please select zones into zoom!", "error", 2000);
    }
};

d3.boxplot.controls.export = function () {
    let select = $("form#export select");
    let selection = parseInt(select.val());
    if (selection > 0) {
        select.val("0");
        dgenies.notify("Not supported yet!", "error", 2000);
    }
};