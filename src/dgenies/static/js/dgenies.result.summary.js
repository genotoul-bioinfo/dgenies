if (!dgenies || !dgenies.result) {
    throw "dgenies.result wasn't included!"
}
dgenies.result.summary = {};
dgenies.result.summary.percents = {};

dgenies.result.summary.show = function(percents) {
    dgenies.result.summary.percents = percents;
    let svgcontainer = d3.select("#draw-stats").html("").append("svg:svg")
        .attr("width", "500px")
        .attr("height", "220px");
    let container = svgcontainer.append("svg:g");
    let percents_order = ["-1", "0", "1", "2", "3"];
    let x = 0;
    let percent_value = 0;
    for (let i in percents_order) {
        let percent = percents_order[i];
        let label=dgenies.result.summary._get_label(percent);
        x += percent_value;
        percent_value = percent in percents ? percents[percent] : 0;
        container.append("rect")
            .attr("x", x + "%")
            .attr("y", 0)
            .attr("width", percent_value + "%")
            .attr("height", "50px")
            .attr("stroke", "none")
            .attr("fill", d3.boxplot.color_idy[d3.boxplot.color_idy_theme][percent]);
        container.append("rect")
            .attr("x", 5)
            .attr("y", 70 + (i * 30))
            .attr("width", "10px")
            .attr("height", "10px")
            .attr("fill", d3.boxplot.color_idy[d3.boxplot.color_idy_theme][percent])
            .style("stroke", "#000")
            .style("stroke-width", "1px");
        container.append("text")
            .attr("x", 30)
            .attr("y", 82 + (i * 30))
            .attr("font-family", "sans-serif")
            .attr("font-size", "12pt")
            .text(label + ":");
        container.append("text")
            .attr("x", 110)
            .attr("y", 82 + (i * 30))
            .attr("font-family", "sans-serif")
            .attr("font-size", "12pt")
            .text(percent_value.toFixed(2) + " %");
    }

    container.append("rect")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", "100%")
        .attr("height", "50px")
        .style("stroke", "#000")
        .style("fill", "none")
        .style("stroke-width", "1px");

    $("#modal-stats").dialog({
        title: "Summary of identity",
        width: "560px",
        buttons: [{
            text: "Export TSV",
            click: dgenies.result.summary.export_tsv
        },{
            text: "Export PNG",
            click: dgenies.result.summary.export_png
        },{
            text: "Export SVG",
            click: dgenies.result.summary.export_svg
        },{
            text: "Close",
            click: function() {
                $(this).dialog("close");
            },
            default: true
        }],
        open: function() { $(this).parents().find(".ui-dialog-buttonpane button")[3].focus() }
    })
};

dgenies.result.summary._get_label = function (percent_class) {
    switch (percent_class) {
            case "-1":
                return "No match";
            case "0":
                return "< 25 %";
            case "1":
                return "< 50 %";
            case "2":
                return "< 75 %";
            case "3":
                return "> 75 %";
        }
};

dgenies.result.summary.get_svg = function () {
    return $("#draw-stats").html();
};

dgenies.result.summary.save_file = function (blob, format) {
    saveAs(blob, `summary_${d3.boxplot.name_y}_to_${d3.boxplot.name_x}.${format}`);
};

dgenies.result.summary.export_tsv = function () {
    let content = "category\tpercent\n";
    for (let percent in dgenies.result.summary.percents) {
        content += `${dgenies.result.summary._get_label(percent)}\t${dgenies.result.summary.percents[percent]}\n`;
    }
    dgenies.result.summary.save_file(new Blob([content], {type: "plain/text"}), "tsv");
};

dgenies.result.summary.export_svg = function () {
    let blob = new Blob([dgenies.result.summary.get_svg()], {type: "image/svg+xml"});
    dgenies.result.summary.save_file(blob, "svg");
};

dgenies.result.summary.export_png = function () {
    let export_div = $("div#export-pict");
    export_div.html("").append($("<canvas>"));
    canvg(export_div.find("canvas")[0], dgenies.result.summary.get_svg());
    let canvas = export_div.find("canvas")[0];
    canvas.toBlob(function(blob) {
        dgenies.result.summary.save_file(blob, "png");
        export_div.html("");
    }, "image/png");
};