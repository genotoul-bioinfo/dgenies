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

/*
 * Export
 */

d3.boxplot.controls.get_svg = function () {
    return "<svg width='5000px' height='5000px' viewBox='0 0 100 100'>" + $("#draw-in").find(">svg").html() + "</svg>";
};

d3.boxplot.controls.save_file = function(blob, format) {
    dgenies.hide_loading();
    saveAs(blob, `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.${format}`);
}

d3.boxplot.controls.export_png = function() {
    let export_div = $("div#export-pict");
    export_div.html("").append($("<canvas>"));
    canvg(export_div.find("canvas")[0], d3.boxplot.controls.get_svg());
    let canvas = export_div.find("canvas")[0];
    canvas.toBlob(function(blob) {
        d3.boxplot.controls.save_file(blob, "png");
        export_div.html("");
    }, "image/png");
};

d3.boxplot.controls.export_svg = function () {
    let transform = d3.boxplot.container.attr("transform");
    let after = function() {
        let blob = new Blob([d3.boxplot.controls.get_svg()], {type: "image/svg+xml"});
        d3.boxplot.zoom.restore_scale(transform);
        d3.boxplot.controls.save_file(blob, "svg");
    };
    d3.boxplot.zoom.reset_scale(true, after);

};

d3.boxplot.controls.export = function () {
    let select = $("form#export select");
    let selection = parseInt(select.val());
    dgenies.show_loading("Building files...", 180);
    window.setTimeout(() => {
        if (selection > 0) {
            if (selection === 1)
                d3.boxplot.controls.export_svg();
            else if (selection === 2)
                d3.boxplot.controls.export_png();
            else
                dgenies.notify("Not supported yet!", "error", 2000);
            dgenies.hide_loading();
            select.val("0");
        }
    }, 0);
};