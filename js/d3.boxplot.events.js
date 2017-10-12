if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.events = {};

d3.boxplot.events.init = function () {
    $("input#filter_size").change(function() {
        d3.boxplot.events.filter_size(d3.boxplot.min_sizes[this.value]);
    });
    $("input#stroke-linecap").change(function() {
        d3.boxplot.events.stroke_linecap(!this.checked);
    });
    $("input#stroke-width").change(function() {
        d3.boxplot.events.stroke_width(this.value);
    })
    $("input#filter_identity").change(function() {
        d3.boxplot.events.filter_identity(this.value);
    })
};

d3.boxplot.events.filter_size = function(min_size) {
    for(let i=0; i<d3.boxplot.min_sizes.length; i++) {
        let size = d3.boxplot.min_sizes[i];
        if (size < min_size) {
            $("path.content-lines.s_" + size.toString().replace(".", "_")).hide();
        }
        else {
            $("path.content-lines.s_" + size.toString().replace(".", "_")).show();
        }
    }
    d3.boxplot.min_size = min_size
};

d3.boxplot.events.filter_identity = function (min_idy) {
    d3.boxplot.min_idy_draw = min_idy;
    $("#loading").show();
    window.setTimeout(() => {
        d3.boxplot.draw_lines();
        d3.boxplot.events.filter_size(d3.boxplot.min_size);
        $("#loading").hide();
    }, 0);
};

d3.boxplot.events.stroke_linecap = function(rounded) {
    d3.boxplot.linecap = rounded ? "round" : "butt";
    $("path").attr("stroke-linecap", d3.boxplot.linecap);
};

d3.boxplot.events.stroke_width = function (width) {
    console.log(width);
    let stroke_width = d3.boxplot.scale / 600;
    if (width === "1") {
        stroke_width = d3.boxplot.scale / 400;
    }
    else if (width === "2") {
        stroke_width = d3.boxplot.scale / 200;
    }
    else if (width === "3") {
        stroke_width = d3.boxplot.scale / 100;
    }
    console.log(stroke_width);
    d3.boxplot.content_lines_width = stroke_width;
    let my_transform = d3.boxplot.container.attr("transform");
    let scale = 1;
    if (my_transform !== null) {
        let search_sc = my_transform.match(/scale\(([-\de.]+)(,\s*([-\de.]+))?\)/);
        let scale_x = parseFloat(search_sc[1]);
        let scale_y = parseFloat(search_sc[3] === undefined ? 0 : search_sc[3]);
        scale = Math.max(scale_x, scale_y);
    }
    d3.selectAll("path.content-lines").attr("stroke-width", stroke_width / scale);
};