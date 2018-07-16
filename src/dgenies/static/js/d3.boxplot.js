if (!d3) {
    throw "d3 wasn't included!"
}
d3.boxplot = {};

//GLOBAL VARIABLES:
d3.boxplot.svgcontainer = null;
d3.boxplot.container = null;
d3.boxplot.svgsupercontainer = null;
d3.boxplot.name_x = null;
d3.boxplot.name_y = null;
d3.boxplot.lines = null;
d3.boxplot.x_len = null;
d3.boxplot.y_len = null;
d3.boxplot.x_zones = null;
d3.boxplot.y_zones = null;
d3.boxplot.zoom_enabled = true;
d3.boxplot.all_disabled = false;
d3.boxplot.min_idy = 0;
d3.boxplot.max_idy = 0;
d3.boxplot.zone_selected = false;
d3.boxplot.query_selected = null;

//For translations:
d3.boxplot.translate_start = null;
d3.boxplot.posX = null;
d3.boxplot.posY = null;
d3.boxplot.old_translate = null;

//Graphical parameters:
d3.boxplot.scale = 1000;
d3.boxplot.content_lines_width = d3.boxplot.scale / 400;
d3.boxplot.break_lines_width = d3.boxplot.scale / 1500;
d3.boxplot.color_idy_theme = "default";
d3.boxplot.color_idy_themes = ["default", "colorblind", "black&white", "r_default", "r_colorblind", "allblack"];
d3.boxplot.color_idy = {
    "default": {
        "3": "#094b09",
        "2": "#2ebd40",
        "1": "#d5670b",
        "0": "#ffd84b",
        "-1": "#fff"
    },
    "colorblind": {
        "3": "#000",
        "2": "#006DDB",
        "1": "#DB6E00",
        "0": "#FFB677",
        "-1": "#fff"
    },
    "black&white": {
        "3": "#000",
        "2": "#626262",
        "1": "#9c9c9c",
        "0": "#DDDCDC",
        "-1": "#fff"
    },
    "r_default": {
        "3": "#7fff65",
        "2": "#238d31",
        "1": "#78410d",
        "0": "#3b080a",
        "-1": "#fff"
    },
    "r_colorblind": {
        "3": "#8c8c8c",
        "2": "#006DDB",
        "1": "#783c00",
        "0": "#312515",
        "-1": "#fff"
    },
    "allblack": {
        "3": "#000",
        "2": "#000",
        "1": "#000",
        "0": "#000",
        "-1": "#fff"
    }
};
d3.boxplot.limit_idy = null;
d3.boxplot.min_idy_draw = 0;
d3.boxplot.min_size = 0;
d3.boxplot.linecap = "round";
d3.boxplot.background_axis = "#f4f4f4";
d3.boxplot.break_lines_color = "#7c7c7c";
d3.boxplot.break_lines_dash = "3, 3";
d3.boxplot.break_lines_show = true;
d3.boxplot.zoom_scale_lines = 1; // Zoom scale used for lines width
d3.boxplot.tick_width = 0.5;
d3.boxplot.color_mixes = "#969696";

//Filter sizes:
d3.boxplot.min_sizes = [0, 0.01, 0.02, 0.03, 0.05, 1, 2];

//Help pictures:
d3.boxplot.help_zoom = "/static/images/ctrl_plus_mouse.png";
d3.boxplot.help_trans = "/static/images/ctrl_plus_click.png";

/**
 * Initialize dotplot
 *
 * @param {string} id_res job id
 * @param {boolean} from_file true to load data from a file (default: false, load from server)
 */
d3.boxplot.init = function (id_res=null, from_file=false) {
    if (id_res === null) {
        id_res = dgenies.result.id_res;
    }
    $("#form-parameters")[0].reset();
    $("form#select-zone")[0].reset();
    if (!from_file) {
        dgenies.post("/get_graph",
            {"id": id_res},
            function (data) {
                if (data["success"]) {
                    d3.boxplot.launch(data);
                }
                else {
                    $("#supdraw").html($("<p>").html("message" in data ? data["message"] : "This job does not exist!").css("margin-top", "15px"));
                    dgenies.result.remove_job_from_cookie(dgenies.result.id_res);
                }
            }
        )
    }
    else {
        dgenies.get(id_res,
            {},
            function (data) {
                d3.boxplot.launch(data);
            })
    }
};

/**
 * Launch draw of dot plot
 *
 * @param {string} res
 * @param {boolean} update if true, just update the existing dot plot (don't initialize events)
 * @param {boolean} noise_change if false, set noise to true
 */
d3.boxplot.launch = function(res, update=false, noise_change=false) {
    dgenies.fill_select_zones(res["x_order"], res["y_order"]);
    if (res["sorted"]) {
        $("input#sort-contigs").val("Undo sort");
        $("#export").find("select option[value=4]").show();
        $("#export").find("select option[value=8]").show();
    }
    else {
        $("input#sort-contigs").val("Sort contigs");
        $("#export").find("select option[value=4]").hide();
        $("#export").find("select option[value=8]").hide();
    }
    d3.boxplot.name_x = res["name_x"];
    d3.boxplot.name_y = res["name_y"];

    if (d3.boxplot.name_x === d3.boxplot.name_y) {
        $("input#sort-contigs").hide();
    }
    else {
        $("input#sort-contigs").show();
    }

    d3.boxplot.lines = res["lines"];
    d3.boxplot.x_len = res["x_len"];
    d3.boxplot.y_len = res["y_len"];
    d3.boxplot.min_idy = res["min_idy"];
    d3.boxplot.max_idy = res["max_idy"];
    d3.boxplot.limit_idy = res["limit_idy"];
    if (!noise_change) {
        dgenies.noise = true;
    }
    $("#hide-noise").val(dgenies.noise ? "Hide noise" : "Show noise");
    d3.boxplot.draw(res["x_contigs"], res["x_order"], res["y_contigs"], res["y_order"]);
    if (!update) {
        $("div#draw").resizable({
            aspectRatio: true
        });
        d3.boxplot.events.init();
        dgenies.result.controls.init();
    }
    if (res["sampled"]) {
        let max_nb_lines = dgenies.numberWithCommas(res["max_nb_lines"].toString());
        dgenies.notify(`<div style="text-align: center"><b>There are too much matches.\nOnly the ${max_nb_lines} best matches are displayed</b></div>`)
    }
    d3.boxplot.mousetip.init();
};

/**
 * Find target chromosome where the user click
 *
 * @param {float} x coordinate on X axis
 * @returns {string|null} chromosome name
 */
d3.boxplot.select_target = function (x) {
    for (let zone in d3.boxplot.x_zones) {
        if (d3.boxplot.x_zones[zone][0] < x && x <= d3.boxplot.x_zones[zone][1]) {
            return zone;
        }
    }
    return null;
};

/**
 * Find query contig where the user click
 *
 * @param {float} y coordinate on Y axis
 * @returns {string|null} contig name
 */
d3.boxplot.select_query = function(y) {
    for (let zone in d3.boxplot.y_zones) {
        if (d3.boxplot.y_zones[zone][0] < y && y <= d3.boxplot.y_zones[zone][1]) {
            return zone;
        }
    }
    return null;
};

/**
 * Find zone (query contig and target chromosome) based on coordinates
 *
 * @param {float} x coordinate on X axis
 * @param {float} y coordinate on Y axis
 * @param {string} x_zone selected chromosome on X axis (target)
 * @param {string} y_zone selected contig on Y axis (query)
 * @param {boolean} force if true, select zone even if a zone is already selected
 */
d3.boxplot.select_zone = function (x=null, y=null, x_zone=null, y_zone=null, force=false) {
    d3.boxplot.mousetip.hide();
    dgenies.show_loading();
    window.setTimeout(() => {
        if (!d3.boxplot.zone_selected || force) {

            if (x_zone === null) {
                //Search zone for X axis:
                x_zone = d3.boxplot.select_target(x)
            }

            if (y_zone === null) {
                //Search zone for Y axis:
                y_zone = d3.boxplot.select_query(y);
            }

            d3.boxplot.zone_selected = [x_zone, y_zone];

            //Compute X and Y scales to zoom into zone:
            let x_len_zone = d3.boxplot.x_zones[x_zone][1] - d3.boxplot.x_zones[x_zone][0];
            let y_len_zone = d3.boxplot.y_zones[y_zone][1] - d3.boxplot.y_zones[y_zone][0];
            let scale_x = d3.boxplot.scale / x_len_zone;
            let scale_y = d3.boxplot.scale / y_len_zone;

            //Zoom in:
            d3.boxplot.container
               .attr("transform", "scale(" + scale_x + "," + scale_y + ")" +
                   "translate(-" + (d3.boxplot.x_zones[x_zone][0]) + ",-" + (d3.boxplot.scale - d3.boxplot.y_zones[y_zone][1]) + ")");
            // Correct lines stroke width to be not impacted by the zoom:
            d3.selectAll(".content-lines").attr("stroke-width", d3.boxplot.content_lines_width / Math.min(scale_x, scale_y));
            d3.boxplot.zoom_scale_lines = Math.min(scale_x, scale_y);
            d3.selectAll("line.break-lines").style("visibility", "hidden");

            //Update left and bottom axis:
            let y_max = d3.boxplot.y_zones[y_zone][1] / d3.boxplot.scale * d3.boxplot.y_len;
            let y_min = d3.boxplot.y_zones[y_zone][0] / d3.boxplot.scale * d3.boxplot.y_len;
            d3.boxplot.draw_left_axis(y_max-y_min, 0);
            let x_max = d3.boxplot.x_zones[x_zone][1] / d3.boxplot.scale * d3.boxplot.x_len;
            let x_min = d3.boxplot.x_zones[x_zone][0] / d3.boxplot.scale * d3.boxplot.x_len;
            d3.boxplot.draw_bottom_axis(x_max - x_min, 0);

            //Update top and right axis:
            let pseudo_x_zones = {};
            pseudo_x_zones[x_zone] = [0, d3.boxplot.x_len];
            d3.boxplot.draw_top_axis(pseudo_x_zones);
            let pseudo_y_zones = {};
            pseudo_y_zones[y_zone] = [0, d3.boxplot.y_len];
            d3.boxplot.draw_right_axis(pseudo_y_zones);

            d3.boxplot.zoom_enabled = false;
        }
        $("#restore-all").show();
        dgenies.hide_loading();
    }, 0);
};

/**
 * Get human readable size in Kb or Mb for a number in bases
 *
 * @param {int} nbases size in bases
 * @param {int} precision unit to use (auto: select according to number size)
 * @param {string} space space before unit (space or non-breaking space for example)
 * @returns {string} human readable size
 */
d3.boxplot.get_human_readable_size = function (nbases, precision=1, space=" ") {
    let lab = "";
    let prec = parseInt("1" + "0".repeat(precision))
    if (nbases > 1000000) {
        lab = (Math.round(nbases / (1000000 / prec)) / prec).toString() + space + "M";
    }
    else if (nbases > 1000) {
        lab = (Math.round(nbases / (1000 / prec)) / prec).toString() + space + "K";
    }
    else {
        lab = Math.round(nbases).toString();
    }
    return lab;
};

/**
 * Draw left axis
 *
 * @param {int} y_max max value of y on the Y axis
 * @param {int} y_min min value of y on the Y axis
 */
d3.boxplot.draw_left_axis = function (y_max, y_min = 0) {
    let axis_length = 500;

    $("svg.left-axis").remove(); //Remove previous axis (if any)

    let svg_left = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("class", "axis left-axis")
        .attr("width", 5)
        .attr("height", 90)
        .attr("x", 0)
        .attr("y", 5)
        .attr("viewBox", "0 0 20 " + axis_length)
        .attr("preserveAspectRatio", "none");

    let container_left = svg_left.append("g")
        .attr("transform", "translate(0," + axis_length + ")rotate(-90)");

    let y_size = y_max - y_min;

    for (let i = 1; i < 10; i++) {
        let y = axis_length / 10 * i;
        let y_t = y_min + y_size / 10 * i;
        if (y_t >= 0 && y_t <= d3.boxplot.y_len) {
            let y_lab = d3.boxplot.get_human_readable_size(y_t);
            container_left.append("line")
                .attr("x1", y)
                .attr("y1", 15)
                .attr("x2", y)
                .attr("y2", 20)
                .attr("stroke-width", d3.boxplot.tick_width)
                .attr("stroke", "black");

            container_left.append("text")
                .attr("x", y)
                .attr("y", 12)
                .attr("text-anchor", "middle")
                .attr("font-family", "sans-serif")
                .attr("font-size", "6.5pt")
                .text(y_lab);
        }
    }
};

/**
 * Draw bottom axis
 *
 * @param {int} x_max max value of x on the X axis
 * @param {int} x_min min value of x on the X axis
 */
d3.boxplot.draw_bottom_axis = function (x_max, x_min = 0) {

    let axis_length = 500;

    $("svg.bottom-axis").remove(); //Remove previous axis (if any)

    let svg_bottom = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("class", "axis bottom-axis")
        .attr("width", 90)
        .attr("height", 5)
        .attr("x", 5)
        .attr("y", 95)
        .attr("viewBox", "0 0 " + axis_length + " 20")
        .attr("preserveAspectRatio", "none");

    let x_size = x_max - x_min;

    for (let i = 1; i < 10; i++) {
        let x = axis_length / 10 * i;
        let x_t = x_min + x_size / 10 * i;
        if (x_t >= 0 && x_t <= d3.boxplot.x_len) {
            let x_lab = d3.boxplot.get_human_readable_size(x_t);
            svg_bottom.append("line")
                .attr("x1", x)
                .attr("y1", 0)
                .attr("x2", x)
                .attr("y2", 5)
                .attr("stroke-width", d3.boxplot.tick_width)
                .attr("stroke", "black");

            svg_bottom.append("text")
                .attr("x", x)
                .attr("y", 15)
                .attr("text-anchor", "middle")
                .attr("font-family", "sans-serif")
                .attr("font-size", "6.5pt")
                .text(x_lab);
        }
    }
};

/**
 * Zoom on left axis
 */
d3.boxplot.zoom_left_axis = function() {
    let transform = d3.boxplot.container.attr("transform");
    if (transform === null) {
        transform = "translate(0,0)scale(1)";
    }
    let tr_regex = /translate\(([^,]+),([^)]+)\)/;
    let translate = parseFloat(transform.match(tr_regex)[2]);
    let sc_regex = /scale\(([^,)]+)(,([^)]+))?\)/;
    let scale = parseFloat(transform.match(sc_regex)[3] !== undefined ? transform.match(sc_regex)[3] : transform.match(sc_regex)[1]);
    let max_y = d3.boxplot.y_len + translate / d3.boxplot.scale * d3.boxplot.y_len / scale;
    let min_y = max_y - d3.boxplot.y_len / scale;
    d3.boxplot.draw_left_axis(max_y, min_y);
};

/**
 * Zoom on bottom axis
 */
d3.boxplot.zoom_bottom_axis = function() {
    let transform = d3.boxplot.container.attr("transform");
    if (transform === null) {
        transform = "translate(0,0)scale(1)";
    }
    let tr_regex = /translate\(([^,]+),([^)]+)\)/;
    let translate = parseFloat(transform.match(tr_regex)[1]);
    let sc_regex = /scale\(([^,)]+)(,([^)]+))?\)/;
    let scale = parseFloat(transform.match(sc_regex)[1]);

    let min_x = -translate / d3.boxplot.scale * d3.boxplot.x_len / scale;
    let max_x = (d3.boxplot.x_len - (translate / d3.boxplot.scale * d3.boxplot.x_len)) / scale;
    d3.boxplot.draw_bottom_axis(max_x, min_x);
};

/**
 * Draw top axis
 *
 * @param {object} x_zones: name of chromosomes of the target
 */
d3.boxplot.draw_top_axis = function (x_zones=d3.boxplot.x_zones) {
    $("svg.top-axis").remove();  //Remove previous axis (if any)
    let transform = d3.boxplot.container.attr("transform");
    if (transform === null) {
        transform = "translate(0,0)scale(1)";
    }
    let tr_regex = /translate\(([^,]+),([^)]+)\)/;
    let translate = parseFloat(transform.match(tr_regex)[1]);
    let sc_regex = /scale\(([^,)]+)(,([^)]+))?\)/;
    let scale = parseFloat(transform.match(sc_regex)[1]);

    let axis_length = 500;
    let svg_top = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("class", "top-axis axis")
        .attr("width", 90)
        .attr("height", 5)
        .attr("x", 5)
        .attr("y", 0)
        .attr("viewBox", "0 0 " + axis_length + " 20")
        .attr("preserveAspectRatio", "none");

    svg_top.append("text")
        .attr("x", axis_length / 2)
        .attr("y", 7.5)
        .attr("font-size", "6pt")
        .attr("font-family", "sans-serif")
        .attr("font-style", "italic")
        .attr("text-anchor", "middle")
        .text(d3.boxplot.name_x);

    let nb_zone = 0;
    for (let zone in x_zones) {
        let x_pos_1 = Math.min(Math.max(x_zones[zone][0] * scale + translate, 0), d3.boxplot.scale);
        let x_pos_2 = Math.min(Math.max(x_zones[zone][1] * scale + translate, 0), d3.boxplot.scale);
        let z_len = x_pos_2 / d3.boxplot.scale * axis_length - x_pos_1 / d3.boxplot.scale * axis_length;
        if (!zone.startsWith("###MIX###")) {
            //z_middle = (x_zones[zone][1] + x_zones[zone][0]) / 2
            let text_container = svg_top.append("svg:svg")
                .attr("x", x_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y", 0)
                .attr("width", z_len)
                .attr("height", "100%");
            let text = text_container.append("text")
                .attr("x", z_len / 2)
                .attr("y", 17)
                .attr("text-anchor", "middle")
                .attr("font-family", "sans-serif")
                .attr("font-size", "6pt")
                .text(zone);
            let zone_txt = zone;
            let i = 4;
            while (text.node().getComputedTextLength() > z_len && zone_txt.length >= 5) {
                text.remove();
                zone_txt = zone.slice(0, -i) + "...";
                text = text_container.append("text")
                    .attr("x", z_len / 2)
                    .attr("y", 17)
                    .attr("text-anchor", "middle")
                    .attr("font-family", "sans-serif")
                    .attr("font-size", "6pt")
                    .text(zone_txt);
                i++;
            }
            if (text.node().getComputedTextLength() > z_len) {
                text.remove();
            }
        }
        if (zone.startsWith("###MIX###")) {
            svg_top.append("rect")
                .attr("x", x_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y", 12)
                .attr("width", z_len)
                .attr("height", 8)
                .attr("fill", d3.boxplot.color_mixes)
                .attr("stroke", d3.boxplot.color_mixes)
        }
        else if (nb_zone > 0) { //Draw zone separator at left of zone (except for first zone)
            svg_top.append("line")
                .attr("x1", x_pos_1 / d3.boxplot.scale * axis_length)
                .attr("x2", x_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y1", 12)
                .attr("y2", 20)
                .attr("stroke", "black")
                .attr("stroke-width", d3.boxplot.tick_width);
        }
        nb_zone++;
    }
};

/**
 * Draw right axis
 *
 * @param {object} y_zones name of contigs of the query
 */
d3.boxplot.draw_right_axis = function (y_zones=d3.boxplot.y_zones) {
    $("svg.right-axis").remove();  //Remove previous axis (if any)
    let transform = d3.boxplot.container.attr("transform");
    if (transform === null) {
        transform = "translate(0,0)scale(1)";
    }
    let tr_regex = /translate\(([^,]+),([^)]+)\)/;
    let translate = parseFloat(transform.match(tr_regex)[2]);
    let sc_regex = /scale\(([^,)]+)(,([^)]+))?\)/;
    let scale = parseFloat(transform.match(sc_regex)[3] !== undefined ? transform.match(sc_regex)[3] : transform.match(sc_regex)[1]);

    let axis_length = 500;
    let svg_right = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("class", "right-axis")
        .attr("width", 5)
        .attr("height", 90)
        .attr("x", 95)
        .attr("y", 5)
        .attr("viewBox", "0 0 20 " + axis_length)
        .attr("preserveAspectRatio", "none");

    let container_right = svg_right.append("g")
        .attr("transform", "translate(20)rotate(90)");

    container_right.append("text")
        .attr("x", axis_length / 2)
        .attr("y", 7.5)
        .attr("font-size", "6pt")
        .attr("font-family", "sans-serif")
        .attr("font-style", "italic")
        .attr("text-anchor", "middle")
        .text(d3.boxplot.name_y);

    let nb_zone = Object.keys(y_zones).length - 1;
    for (let zone in y_zones) {
        let y_pos_2 = Math.min(Math.max((d3.boxplot.scale - y_zones[zone][0]) * scale + translate, 0), d3.boxplot.scale);
        let y_pos_1 = Math.min(Math.max((d3.boxplot.scale - y_zones[zone][1]) * scale + translate, 0), d3.boxplot.scale);
        let z_len = y_pos_2 / d3.boxplot.scale * axis_length - y_pos_1 / d3.boxplot.scale * axis_length;
        if (!zone.startsWith("###MIX###")) {
            //z_middle = (x_zones[zone][1] + x_zones[zone][0]) / 2
            let text_container = container_right.append("svg:svg")
                .attr("x", y_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y", 0)
                .attr("width", z_len)
                .attr("height", "100%");
            let text = text_container.append("text")
                .attr("x", z_len / 2)
                .attr("y", 17)
                .attr("text-anchor", "middle")
                .attr("font-family", "sans-serif")
                .attr("font-size", "6pt")
                .text(zone);
            let zone_txt = zone;
            let i = 4;
            while (text.node().getComputedTextLength() > z_len && zone_txt.length >= 5) {
                text.remove();
                zone_txt = zone.slice(0, -i) + "...";
                text = text_container.append("text")
                    .attr("x", z_len / 2)
                    .attr("y", 17)
                    .attr("text-anchor", "middle")
                    .attr("font-family", "sans-serif")
                    .attr("font-size", "6pt")
                    .text(zone_txt);
                i++;
            }
            if (text.node().getComputedTextLength() > z_len) {
                text.remove();
            }
        }
        if (zone.startsWith("###MIX###")) {
            container_right.append("rect")
                .attr("x", y_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y", 12)
                .attr("width", z_len)
                .attr("height", 8)
                .attr("fill", d3.boxplot.color_mixes)
                .attr("stroke", "None")
        }
        else if (nb_zone > 0) { //Draw zone separator at left of zone (except for first zone)
            container_right.append("line")
                .attr("x1", y_pos_1 / d3.boxplot.scale * axis_length)
                .attr("x2", y_pos_1 / d3.boxplot.scale * axis_length)
                .attr("y1", 12)
                .attr("y2", 20)
                .attr("stroke", "black")
                .attr("stroke-width", d3.boxplot.tick_width)
                .attr("class", "whereis");
        }
        nb_zone--;
    }
};

/**
 * Draw backgrounds of all axis
 */
d3.boxplot.draw_axis_bckgd = function () {
    // Top:
    let svg_top = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("width", 100)
        .attr("height", 5)
        .attr("x", 0)
        .attr("y", 0)
        .attr("viewBox", "0 0 100 5")
        .attr("preserveAspectRatio", "none");
    svg_top.append("polygon")
        .attr("points", "5,0 95,0 100,5 0,5")
        .attr("stroke", "none")
        .style("fill", d3.boxplot.background_axis);

    // Right:
    let svg_right = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("width", 5)
        .attr("height", 100)
        .attr("x", 95)
        .attr("y", 0)
        .attr("viewBox", "0 0 5 100")
        .attr("preserveAspectRatio", "none");
    svg_right.append("polygon")
        .attr("points", "0,0 5,5 5,95 0,100")
        .attr("stroke","none")
        .style("fill", d3.boxplot.background_axis);

    // Bottom:
    let svg_bottom = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("width", 100)
        .attr("height", 5)
        .attr("x", 0)
        .attr("y", 95)
        .attr("viewBox", "0 0 100 5")
        .attr("preserveAspectRatio", "none");
    svg_bottom.append("polygon")
        .attr("points", "0,0 100,0 95,5 5,5")
        .attr("stroke", "none")
        .style("fill", d3.boxplot.background_axis);

    //Left:
    let svg_left = d3.boxplot.svgsupercontainer.append("svg:svg")
        .attr("width", 5)
        .attr("height", 100)
        .attr("x", 0)
        .attr("y", 0)
        .attr("viewBox", "0 0 5 100")
        .attr("preserveAspectRatio", "none");
    svg_left.append("polygon")
        .attr("points", "5,0 5,100 0,95 0,5")
        .attr("stroke", d3.boxplot.background_axis)
        .attr("stroke-width", "0px")
        .style("fill", d3.boxplot.background_axis);
};

/**
 * Sort function key for color identity
 *
 * @param a
 * @param b
 * @returns {number}
 * @private
 */
d3.boxplot._sort_color_idy = function(a, b) {
    return parseFloat(b) - parseFloat(a);
};

/**
 * Draw legend
 */
d3.boxplot.draw_legend = function () {
    d3.select("#legend .draw").html(""); //Empty legend
    let color_idy = d3.boxplot.color_idy[d3.boxplot.color_idy_theme];
    let color_idy_len = Object.keys(color_idy).length;
    let color_idy_order = ["3", "2", "1", "0"];
    let color_idy_labels = [d3.boxplot.limit_idy[2].toString(), d3.boxplot.limit_idy[1].toString(),
                            d3.boxplot.limit_idy[0].toString(), "0"];
    let svgcontainer = d3.select("#legend .draw").append("svg:svg")
        .attr("width", "100%")
        .attr("height", "99%");
    let draw = $("#legend").find(".draw");
    let draw_w = draw.width();
    let draw_h = draw.height();
    let container = svgcontainer.append("g");
    for (let i = 0; i < color_idy_order.length; i++) {
        let color_idy_idx = color_idy_order[i];
        container.append("rect")
            .attr("x", "50%")
            .attr("y", (i * (100 / color_idy_len)) + "%")
            .attr("width", "50%")
            .attr("height", (100 / color_idy_len) + "%")
            .attr("stroke", "none")
            .attr("fill", color_idy[color_idy_idx]);
        container.append("text")
            .attr("x", "45%")
            .attr("y", ((i * (100 / color_idy_len)) + (100 / color_idy_len)-1) + "%")
            .attr("text-anchor", "end")
            .attr("font-family", "sans-serif")
            .attr("font-size", "10pt")
            .text(color_idy_labels[i]);
    }
    container.append("text")
            .attr("x", "45%")
            .attr("y", 10)
            .attr("text-anchor", "end")
            .attr("font-family", "sans-serif")
            .attr("font-size", "10pt")
            .text("1");
    container.append("text")
        .attr("x", 0)
        .attr("y", "50%")
        .attr("text-anchor", "middle")
        .attr("transform", "translate(-" + (draw_w - 15) + "," + (draw_h / 2) + ")rotate(-90)")
        .attr("font-family", "sans-serif")
        .attr("font-size", "11.5pt")
        .attr("font-weight", "bold")
        .text("Identity")

};

/**
 * Get length of a given line
 *
 * @param {array} line line object
 * @returns {number} line length
 * @private
 */
d3.boxplot._get_line_len = function (line) {
    let x1 = line[0] / d3.boxplot.x_len * d3.boxplot.scale;
    let x2 = line[1] / d3.boxplot.x_len * d3.boxplot.scale;
    let y1 = d3.boxplot.scale - (line[2] / d3.boxplot.y_len * d3.boxplot.scale);
    let y2 = d3.boxplot.scale - (line[3] / d3.boxplot.y_len * d3.boxplot.scale);
    return Math.sqrt(Math.pow(x2-x1, 2) + Math.pow(y2-y1, 2));
};

/**
 * Sort lines with their length (DESC)
 *
 * @param {array} l1 line object
 * @param {array} l2 line object
 * @returns {number}
 * @private
 */
d3.boxplot._sort_lines = function(l1, l2) {
    return d3.boxplot._get_line_len(l2) - d3.boxplot._get_line_len(l1);
};

/**
 * Sort lines with their identity (DESC)
 *
 * @param {array} l1 line object
 * @param {array} l2 line object
 * @returns {number}
 * @private
 */
d3.boxplot._sort_lines_by_idy = function(l1, l2) {
    return l1[4] - l2[4];
};

/**
 * Build line data for D3.js
 *
 * @param {object} d data object of the line
 * @param {int} min_size min size of line. Beside it, don't draw the line
 * @param {int|null} max_size max size of line. Over it, don't draw the line
 * @param {number} x_len length of x (target)
 * @param {number} y_len length of y (query)
 * @returns {string} path object
 * @private
 */
d3.boxplot.__lineFunction = function(d, min_size=0, max_size=null, x_len, y_len) {
    d = d.sort(d3.boxplot._sort_lines_by_idy);
    let path = [];
    for (let i=0; i < d.length; i++) {
        let d_i = d[i];
        let x1 = d_i[0] / x_len * d3.boxplot.scale;
        let x2 = d_i[1] / x_len * d3.boxplot.scale;
        let y1 = d3.boxplot.scale - (d_i[2] / y_len * d3.boxplot.scale);
        let y2 = d3.boxplot.scale - (d_i[3] / y_len * d3.boxplot.scale);
        let idy = d_i[4];
        let len = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
        if (len > min_size && (max_size === null || len < max_size) && Math.abs(idy) >= d3.boxplot.min_idy_draw) {
            path.push(`M${x1} ${y1} L${x2} ${y2}`);
        }
    }
    return path.join(" ")
};

/**
 * Draw matches on dot plot for the given identity class
 *
 * @param {string} idy identity class of matches to draw
 * @param {object} lines matches definitions
 * @param {number} x_len total length of target
 * @param {number} y_len total length of query
 * @private
 */
d3.boxplot.__draw_idy_lines = function (idy, lines, x_len, y_len) {
    let min_sizes = d3.boxplot.min_sizes;
    for (let i=0; i<min_sizes.length; i++) {
        let min_size = min_sizes[i];
        let max_size = i + 1 < min_sizes.length ? min_sizes[i + 1] : null;
        if (lines[idy].length > 0) {
            d3.boxplot.container.append("path")
                .attr("d", d3.boxplot.__lineFunction(lines[idy], min_size, max_size, x_len, y_len))
                .attr("class", "content-lines s_" + min_size.toString().replace(".", "_") + " idy_" + idy)
                .attr("stroke-width", d3.boxplot.content_lines_width + "px")
                .attr("stroke", d3.boxplot.color_idy[d3.boxplot.color_idy_theme][idy])
                .attr("stroke-linecap", d3.boxplot.linecap);
        }
    }
};

/**
 * Switch to next color theme
 */
d3.boxplot.switch_color_theme = function () {
    if (!d3.boxplot.all_disabled) {
        let current_theme = d3.boxplot.color_idy_theme;
        let idx = d3.boxplot.color_idy_themes.indexOf(current_theme);
        if (idx < d3.boxplot.color_idy_themes.length - 1) {
            idx++;
        }
        else {
            idx = 0;
        }
        d3.boxplot.change_color_theme(d3.boxplot.color_idy_themes[idx]);
    }
};

/**
 * Change color theme to the given one
 *
 * @param {string} theme theme name
 */
d3.boxplot.change_color_theme = function (theme) {
    if (d3.boxplot.color_idy_themes.indexOf(theme) === -1) {
        throw "Theme not valid!"
    }
    for (let idy=0; idy <4; idy++) {
        d3.boxplot.color_idy_theme = theme;
        d3.boxplot.container.selectAll("path.idy_" + idy.toString())
            .attr("stroke", d3.boxplot.color_idy[d3.boxplot.color_idy_theme][idy])
    }
    d3.boxplot.draw_legend();
};

/**
 * Draw matches on dot plot
 *
 * @param {object} lines matches definition
 * @param {number} x_len total len of target
 * @param {number} y_len total len of query
 */
d3.boxplot.draw_lines = function (lines=d3.boxplot.lines, x_len=d3.boxplot.x_len, y_len=d3.boxplot.y_len) {

    //Remove old lines (if any):
    $("path.content-lines").remove();

    //lines = lines.sort(d3.boxplot._sort_lines);
    for (let i=0; i <4; i++) {
        d3.boxplot.__draw_idy_lines(i.toString(), lines, x_len, y_len)
    }

    d3.boxplot.events.filter_size(d3.boxplot.min_size);
};

/**
 * Draw dot plot
 *
 * @param {object} x_contigs length associated to each contig of the query
 * @param {array} x_order order of query contigs
 * @param {object} y_contigs length associated to each chromosome of the target
 * @param {array} y_order order of target chromosomes
 */
d3.boxplot.draw = function (x_contigs, x_order, y_contigs, y_order) {
    let width = 850;
    let height = 850;
    $("div#draw").width(width)
        .height(height);
    let draw = $("#draw");
    draw.empty();
    draw.append($("<div>")
        .attr("id", "restore-all").css("display", "none").attr("title", "Unzoom"));
    let draw_in = draw.append($("<div>").attr("id", "draw-in"));
    d3.boxplot.svgsupercontainer = d3.select("#draw-in").append("svg:svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", "0 0 100 100")
        .attr("preserveAspectRatio", "none");
    let drawcontainer = d3.boxplot.svgsupercontainer.append("svg:g")
        .attr("class", "drawcontainer");
    drawcontainer.append("rect")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("stroke", "none")
        .attr("fill", "white");
    d3.boxplot.svgcontainer = drawcontainer.append("svg:svg")
        .attr("class", "svgcontainer")
        .attr("width", 90)
        .attr("height", 90)
        .attr("x", 5)
        .attr("y", 5)
        .attr("viewBox", "0 0 " + d3.boxplot.scale + " " + d3.boxplot.scale)
        .attr("preserveAspectRatio", "none");

    d3.boxplot.container = d3.boxplot.svgcontainer.append("svg:g")
        .attr("class", "container");

    d3.boxplot.container.append("rect")
        .attr("x", 0)
        .attr("y", 0)
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("stroke", "none")
        .attr("fill", "white");

    //X axis:
    d3.boxplot.x_zones = {};
    let sum = 0;
    for (let i = 0; i < x_order.length - 1; i++) {
        let x_id = x_order[i];
        let x_contig_len = x_contigs[x_id] / d3.boxplot.x_len * d3.boxplot.scale;
        d3.boxplot.x_zones[x_id] = [sum, sum + x_contig_len];
        sum += x_contig_len;

        d3.boxplot.container.append("line")
            .attr("x1", sum)
            .attr("y1", d3.boxplot.scale)
            .attr("x2", sum)
            .attr("y2", 0)
            .attr("class", "break-lines")
            .attr("stroke-width", d3.boxplot.break_lines_width)
            .attr("stroke", d3.boxplot.break_lines_color)
            .style("stroke-dasharray", d3.boxplot.break_lines_dash);
    }
    d3.boxplot.x_zones[x_order[x_order.length - 1]] = [sum, d3.boxplot.scale];

    //Y axis:
    d3.boxplot.y_zones = {};
    sum = 0;
    for (let i = 0; i < y_order.length - 1; i++) {
        let y_id = y_order[i];
        let y_contig_len = y_contigs[y_id] / d3.boxplot.y_len * d3.boxplot.scale;
        d3.boxplot.y_zones[y_id] = [sum, sum + y_contig_len];
        sum += y_contig_len;

        d3.boxplot.container.append("line")
            .attr("x1", 0)
            .attr("y1", d3.boxplot.scale - sum)
            .attr("x2", d3.boxplot.scale)
            .attr("y2", d3.boxplot.scale - sum)
            .attr("class", "break-lines")
            .attr("stroke-width", d3.boxplot.break_lines_width)
            .attr("stroke", d3.boxplot.break_lines_color)
            .style("stroke-dasharray", d3.boxplot.break_lines_dash);
    }
    d3.boxplot.y_zones[y_order[y_order.length - 1]] = [sum, d3.boxplot.scale];

    if (!d3.boxplot.break_lines_show) {
        d3.selectAll("line.break-lines").style("visibility", "hidden");
    }

    d3.boxplot.draw_axis_bckgd();
    d3.boxplot.draw_left_axis(d3.boxplot.y_len);
    d3.boxplot.draw_bottom_axis(d3.boxplot.x_len);
    d3.boxplot.draw_top_axis(d3.boxplot.x_zones);
    d3.boxplot.draw_right_axis(d3.boxplot.y_zones);

    window.setTimeout(() => {
        //Data:
        d3.boxplot.draw_lines();

        $("#restore-all").click(function () {
            if (d3.boxplot.zoom.reset_scale(false, null, false)) {
                $(this).hide();
            }
        });

        $(document).on("keyup", function(e) {
            if (e.keyCode === 27) {
                if(d3.boxplot.zoom.reset_scale(false, null, false)) {
                    $("#restore-all").hide();
                }
            }
        });

        d3.boxplot.draw_legend();

        dgenies.hide_loading();
    }, 0);

    draw.append($("<div>").attr("id", "help-zoom")
                          .append("Press CTRL to zoom")
                          .append($("<img>").attr("src", d3.boxplot.help_zoom)
                                            .attr("alt", "")).hide().on("click", function() {$(this).hide()}));

    draw.append($("<div>").attr("id", "help-trans")
                          .append("Press CTRL to translate")
                          .append($("<img>").attr("src", d3.boxplot.help_trans)
                                            .attr("alt", "")).hide().on("click", function() {$(this).hide()})
        .on("mouseup", function() {d3.boxplot.translate_start = null; $("#help-trans").fadeOut("slow");}));

    d3.boxplot.zoom.init();

    d3.boxplot.events.init_context_menu();
};
