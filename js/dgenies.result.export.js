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
    dgenies.show_loading("Building files...", 180);
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
    dgenies.show_loading("Building files...", 180);
    let transform = d3.boxplot.container.attr("transform");
    let after = function() {
        let blob = new Blob([dgenies.result.export.get_svg()], {type: "image/svg+xml"});
        d3.boxplot.zoom.restore_scale(transform);
        dgenies.result.export.save_file(blob, "svg");
    };
    d3.boxplot.zoom.reset_scale(true, after);

};

dgenies.result.export.export_paf = function () {
    dgenies.show_loading("Building files...", 180);
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/paf/${dgenies.result.id_res}`)
        .attr("download", `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.paf`).attr("id", "my-download").text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

dgenies.result.export.dl_fasta = function (gzip=false) {
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/fasta-query/${dgenies.result.id_res}`)
        .attr("download", d3.boxplot.name_y + (gzip ? ".fasta.gz" : ".fasta")).attr("id", "my-download").text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

dgenies.result.export.export_fasta = function(compress=false) {
    dgenies.show_loading("Building files...", 180);
    dgenies.post("/get-fasta-query/" + dgenies.result.id_res,
        {
            gzip: compress
        },
        function(data, success) {
            if (data["status"] === 0) {
                window.setTimeout(() => {
                    dgenies.result.export.export_fasta();
                }, 10000)
            }
            else if (data["status"] === 2) {
                dgenies.result.export.dl_fasta(data["gzip"]);
            }
            else if (data["status"] === 1) {
                dgenies.hide_loading();
                dgenies.notify("We are building your Fasta file. You will receive by mail a link to download it soon!",
                    "info");
            }
            else {
                dgenies.hide_loading();
                dgenies.notify("An error has occurred. Please contact us to report the bug", "danger");
            }
        });
};

dgenies.result.export.ask_export_fasta = function () {
    let dialog = $("<div>")
        .attr("id", "dialog-confirm")
        .attr("title", "Gzip?");
    let icon = $("<span>")
        .attr("class", "ui-icon ui-icon-help")
        .css("float", "left")
        .css("margin", "12px 12px 20px 0");
    let body = $("<p>");
    body.append(icon);
    body.append("Compression is recommanded on slow connections. Download Gzip file?");
    dialog.append(body);
    dialog.dialog({
        resizable: false,
        height: "auto",
        width: 500,
        modal: true,
        buttons: {
            "Use default": function() {
                $( this ).dialog( "close" );
                dgenies.result.export.export_fasta(false);
            },
            "Use Gzip": function () {
                $( this ).dialog( "close" );
                dgenies.result.export.export_fasta(true);
            },
            Cancel: function () {
                $( this ).dialog( "close" );
            }
        }
    })
};

dgenies.result.export.export = function () {
    let select = $("form#export select");
    let selection = parseInt(select.val());
    window.setTimeout(() => {
        if (selection > 0) {
            let async = false;
            if (selection === 1)
                dgenies.result.export.export_svg();
            else if (selection === 2)
                dgenies.result.export.export_png();
            else if (selection === 3)
                dgenies.result.export.export_paf();
            else if (selection === 4) {
                dgenies.result.export.ask_export_fasta();
                async = true;
            }
            else
                dgenies.notify("Not supported yet!", "danger", 2000);
            if (!async)
                dgenies.hide_loading();
            select.val("0");
        }
    }, 0);
};