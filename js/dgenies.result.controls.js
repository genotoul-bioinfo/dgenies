if (!dgenies || !dgenies.result) {
    throw "dgenies.result wasn't included!"
}
dgenies.result.controls = {};

dgenies.result.controls.init = function () {
    $("#sort-contigs").click(dgenies.result.controls.launch_sort_contigs);
    $("form#select-zone input.submit").click(dgenies.result.controls.select_zone);
    $("form#export select").change(dgenies.result.export.export);
};

dgenies.result.controls.launch_sort_contigs = function () {
    d3.boxplot.zoom.reset_scale();
    window.setTimeout(() => {
        dgenies.show_loading("Building...");
        window.setTimeout(() => {
            $.post(`/sort/${d3.boxplot.id_res}`,
                {},
                function (data) {
                    if (!data["success"]) {
                        dgenies.hide_loading();
                        alert("An error occurred!");
                    }
                }
            );
        }, 0);
    }, 0);
};

dgenies.result.controls.select_zone = function() {
    let contig_select = $("#select-contig").find(":selected");
    let target_select = $("#select-target").find(":selected");
    if (parseInt(contig_select.val()) > 0 && parseInt(target_select.val())) {
        d3.boxplot.select_zone(null, null, target_select.text(), contig_select.text(), true);
    }
    else {
        dgenies.notify("Please select zones into zoom!", "error", 2000);
    }
};