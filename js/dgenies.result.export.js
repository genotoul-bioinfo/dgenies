if (!dgenies || !dgenies.result) {
    throw "dgenies.result wasn't included!"
}
dgenies.result.export = {};


dgenies.result.export.get_svg = function () {
    return "<svg width='5000px' height='5000px' viewBox='0 0 100 100'>" + $("#draw-in").find(">svg").html() + "</svg>";
};

dgenies.result.export.save_file = function(blob, format) {
    dgenies.hide_loading();
    saveAs(blob, `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.${format}`);
}

dgenies.result.export.export_png = function() {
    let export_div = $("div#export-pict");
    export_div.html("").append($("<canvas>"));
    canvg(export_div.find("canvas")[0], dgenies.result.export.get_svg());
    let canvas = export_div.find("canvas")[0];
    canvas.toBlob(function(blob) {
        dgenies.result.export.save_file(blob, "png");
        export_div.html("");
    }, "image/png");
};

dgenies.result.export.export_svg = function () {
    let transform = d3.boxplot.container.attr("transform");
    let after = function() {
        let blob = new Blob([dgenies.result.export.get_svg()], {type: "image/svg+xml"});
        d3.boxplot.zoom.restore_scale(transform);
        dgenies.result.export.save_file(blob, "svg");
    };
    d3.boxplot.zoom.reset_scale(true, after);

};

dgenies.result.export.export_paf = function () {
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/paf/${dgenies.result.id_res}`)
        .attr("download", `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.paf`).attr("id", "my-download").text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

dgenies.result.export.export = function () {
    let select = $("form#export select");
    let selection = parseInt(select.val());
    dgenies.show_loading("Building files...", 180);
    window.setTimeout(() => {
        if (selection > 0) {
            if (selection === 1)
                dgenies.result.export.export_svg();
            else if (selection === 2)
                dgenies.result.export.export_png();
            else if (selection === 3)
                dgenies.result.export.export_paf();
            else
                dgenies.notify("Not supported yet!", "danger", 2000);
            dgenies.hide_loading();
            select.val("0");
        }
    }, 0);
};