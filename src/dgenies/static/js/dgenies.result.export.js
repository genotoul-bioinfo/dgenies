if (!dgenies || !dgenies.result) {
    throw "dgenies.result wasn't included!"
}
dgenies.result.export = {};

/**
 * Build SVG tag and content
 *
 * @param {string} width svg width size (with unit [px])
 * @returns {string} svg tag and content
 */
dgenies.result.export.get_svg = function (width="5000px") {
    return `<svg version='1.1' xmlns='http://www.w3.org/2000/svg' width='${width}' height='${width}' viewBox='0 0 100 100'>${$("#draw-in").find(">svg").html()}</svg>`;
};

/**
 * Save file
 * @param {Blob} blob file content to save
 * @param {string} format file format
 */
dgenies.result.export.save_file = function(blob, format) {
    dgenies.hide_loading();
    saveAs(blob, `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.${format}`);
};

/**
 * Export dot plot as PNG
 */
dgenies.result.export.export_png = function() {
    dgenies.show_loading("Building picture...", 210);
    window.setTimeout(() => {
        let export_div = $("div#export-pict");
        export_div.html("").append($("<canvas>"));
        canvg(export_div.find("canvas")[0], dgenies.result.export.get_svg());
        let canvas = export_div.find("canvas")[0];
        canvas.toBlob(function (blob) {
            dgenies.result.export.save_file(blob, "png");
            export_div.html("");
        }, "image/png");
    }, 0);
};

/**
 * Export dot plot as SVG
 */
dgenies.result.export.export_svg = function () {
    dgenies.show_loading("Building picture...", 180);
    window.setTimeout(() => {
        let svg = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\" " +
                  "\"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\">";
        svg += dgenies.result.export.get_svg("1000px");
        let blob = new Blob([svg], {type: "image/svg+xml"});
        //d3.boxplot.zoom.restore_scale(transform);
        dgenies.result.export.save_file(blob, "svg");
    }, 0);
};

/**
 * Download PAF alignment file
 */
dgenies.result.export.export_paf = function () {
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/paf/${dgenies.result.id_res}`)
        .attr("download", `map_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.paf`).attr("id", "my-download").text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

/**
 * Download query fasta file
 * @param {boolean} gzip if true, gzip the file
 */
dgenies.result.export.dl_fasta = function (gzip=false) {
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/fasta-query/${dgenies.result.id_res}`)
        .attr("download", d3.boxplot.name_y + (gzip ? ".fasta.gz" : ".fasta")).attr("id", "my-download").text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

/**
 * Export fasta file
 * @param {boolean} compress if true compress (gzip) the file
 */
dgenies.result.export.export_fasta = function(compress=false) {
    dgenies.show_loading("Building file...", 180);
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

/**
 * Show export dialog
 */
dgenies.result.export.ask_export_fasta = function () {
    if (dgenies.mode === "webserver") {
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
                "Use default": function () {
                    $(this).dialog("close");
                    dgenies.result.export.export_fasta(false);
                },
                "Use Gzip": function () {
                    $(this).dialog("close");
                    dgenies.result.export.export_fasta(true);
                },
                Cancel: function () {
                    $(this).dialog("close");
                }
            }
        });
    }
    else {
        dgenies.result.export.export_fasta(false);
    }
};

/**
 * Download association table between queries and targets
 */
dgenies.result.export.export_association_table = function () {
    let export_div = $("div#export-pict");
    export_div.html("");
    export_div.append($("<a>").attr("href", `/qt-assoc/${dgenies.result.id_res}`)
        .attr("download", d3.boxplot.name_y + "_" + d3.boxplot.name_x + "_assoc.tsv").attr("id", "my-download")
        .text("download"));
    dgenies.hide_loading();
    document.getElementById('my-download').click();
};

/**
 * Download backup file of the project
 */
dgenies.result.export.export_backup_file = function() {
    dgenies.show_loading("Building file...", 180);
    window.setTimeout(() => {
        let export_div = $("div#export-pict");
        export_div.html("");
        export_div.append($("<a>").attr("href", `/backup/${dgenies.result.id_res}`)
            .attr("download", d3.boxplot.name_y + "_" + d3.boxplot.name_x + "_" + dgenies.result.id_res + ".tar.gz").attr("id", "my-download")
            .text("download"));
        dgenies.hide_loading();
        document.getElementById('my-download').click();
    });
};

/**
 * Export list of contigs with no association with any target or any query
 * @param {string} to: query or target
 */
dgenies.result.export.export_no_association_file = function (to) {
    window.setTimeout(() => {
        dgenies.show_loading("Building file...", 180);
        let on = to === "query" ? "target" : "query";
        dgenies.post("/no-assoc/" + dgenies.result.id_res,
            {"to": to},
            function (data, success) {
            dgenies.hide_loading();
                if (!data["empty"]) {
                    let blob = new Blob([data["file_content"]], {type: "text/plain"});
                    saveAs(blob, `no_${to}_matches_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.txt`);
                }
                else {
                    dgenies.notify(`No contigs in ${to} have None match with any ${on}!`, "success")
                }
            })
    }, 0);
};

/**
 * Export query like reference fasta file (webserver mode)
 */
dgenies.result.export.export_query_as_reference_fasta_webserver = function() {
    dgenies.post(`/build-query-as-reference/${dgenies.result.id_res}`,
        {},
        function (data, success) {
            if (data["success"]) {
                dgenies.notify("You will receive a mail soon with the link to download your Fasta file", "success")
            }
            else {
                dgenies.notify(`An error has occurred. Please contact the support`, "danger")
            }
        });
};

/**
 * Export query like reference fasta file (standalone mode)
 */
dgenies.result.export.export_query_as_reference_fasta_standalone = function () {
    dgenies.show_loading("Building file...", 180);
    window.setTimeout(() => {
        dgenies.post(`/build-query-as-reference/${dgenies.result.id_res}`,
        {},
        function (data, success) {
            if (data["success"]) {
                let export_div = $("div#export-pict");
                export_div.html("");
                export_div.append($("<a>").attr("href", `/get-query-as-reference/${dgenies.result.id_res}`)
                    .attr("download", `as_reference_${d3.boxplot.name_y}.fasta`)
                    .attr("id", "my-download").text("download"));
                document.getElementById('my-download').click();
                dgenies.hide_loading();
            }
            else {
                dgenies.notify(`An error has occurred. Please contact the support`, "danger")
            }
        });
    }, 0);
};

/**
 * Download offline viewer
 */
dgenies.result.export.export_offline_viewer = function() {
    dgenies.show_loading("Building file...", 180);
    window.setTimeout(() => {
        dgenies.post(`/summary/${dgenies.result.id_res}`,
            {},
            function (data) {
                dgenies.hide_loading();
                if (data["success"]) {
                    if (data["status"] === "done") {
                        let export_div = $("div#export-pict");
                        export_div.html("");
                        export_div.append($("<a>").attr("href", `/viewer/${dgenies.result.id_res}`)
                            .attr("download", d3.boxplot.name_y + "_" + d3.boxplot.name_x + "_" +
                                dgenies.result.id_res + ".html").attr("id", "my-download")
                            .text("download"));
                        dgenies.hide_loading();
                        document.getElementById('my-download').click();
                    }
                    else if (data["status"] === "waiting") {
                        dgenies.result.export.export_offline_viewer();
                    }
                }
                else {
                    dgenies.notify(data["message"] || "An error occurred! Please contact us to report the bug", "danger");
                }
            })
    }, 0);
};

/**
 * Manage exports
 */
dgenies.result.export.export = function () {
    let select = $("form#export select");
    let selection = parseInt(select.val());
    window.setTimeout(() => {
        if (selection > 0) {
            let async = false;
            if (selection === 1) {
                dgenies.result.export.export_svg();
                async = true;
            }
            else if (selection === 2) {
                dgenies.result.export.export_png();
                async = true;
            }
            else if (selection === 3)
                dgenies.result.export.export_paf();
            else if (selection === 4) {
                dgenies.result.export.ask_export_fasta();
                async = true;
            }
            else if (selection === 5) {
                dgenies.result.export.export_association_table();
            }
            else if (selection === 6) {
                dgenies.result.export.export_no_association_file("query");
                async = true;
            }
            else if (selection === 7) {
                dgenies.result.export.export_no_association_file("target");
                async = true;
            }
            else if (selection === 8) {
                if (dgenies.mode === "webserver") {
                    dgenies.result.export.export_query_as_reference_fasta_webserver();
                }
                else {
                    dgenies.result.export.export_query_as_reference_fasta_standalone();
                    async = true;
                }
            }
            else if (selection === 9) {
                dgenies.result.export.export_backup_file();
                async = true;
            }
            else if (selection === 10) {
                dgenies.result.export.export_offline_viewer();
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