if (!d3 || !d3.dgenies) {
    throw "d3.dgenies wasn't included!"
}


d3.dgenies.mousetip = {};

d3.dgenies.mousetip.dotplot = {};
d3.dgenies.mousetip.track_x = {};
d3.dgenies.mousetip.track_y = {};

/**
 * Get color (black/white) depending on bgColor so it would be clearly seen.
 *
 * @param bgColor
 * @returns {string}
 */
d3.dgenies.mousetip.getColorByBgColor = function(bgColor) {
    if (!bgColor) { return ''; }
    return (parseInt(bgColor.replace('#', ''), 16) > 0xffffff / 2) ? '#000' : '#fff';
}

/**
 * Mouse tip basis for dotplot
 *
 * @param my_tip
 * @param relative_to
 * @param {int} x
 * @param {int} y
 */
$.fn.mousetip_dotplot = function(my_tip, relative_to=null, x=20, y=20) {

    let $this = $(this);
    let tip = relative_to === null ? $(my_tip, this) : $(my_tip, relative_to);
    let hidden = true;

    $this.hover(function(e) {
        if (!e.ctrlKey) {
            tip.show();
            hidden = false;
        }

    }, function() {
        hidden = true;
        tip.hide().removeAttr('style');

    }).mousemove(function (e) {

        tip.hide();

        window.setTimeout(() => {

            let rect = relative_to === null ? this.getBoundingClientRect() : $(relative_to)[0].getBoundingClientRect();
            let posX = rect.left + window.scrollX,
                posY = rect.top + window.scrollY,
                m_x = e.pageX - rect.left - window.scrollX,
                m_y = e.pageY - rect.top - window.scrollY;

            let mouseX = m_x + (x);
            let mouseY = m_y + (y);

            let rect_g = $("g.container")[0].getBoundingClientRect();
            let posX_g = rect_g.left + window.scrollX,
                posY_g = rect_g.top + window.scrollY,
                width_c = rect_g.width,
                height_c = rect_g.height;
            let x_g = (e.pageX - posX_g) / width_c * d3.dgenies.scale,
                y_g = d3.dgenies.scale - ((e.pageY - posY_g) / height_c * d3.dgenies.scale);

            let match = d3.dgenies.mousetip.dotplot.get_match(e);

            let x_zone = "unknown";
            for (let zone in d3.dgenies.x_zones) {
                if (d3.dgenies.x_zones[zone][0] < x_g && x_g <= d3.dgenies.x_zones[zone][1]) {
                    x_zone = d3.dgenies.mousetip.get_label(zone);
                    break;
                }
            }
            let y_zone = "unknown";
            for (let zone in d3.dgenies.y_zones) {
                if (d3.dgenies.y_zones[zone][0] < y_g && y_g <= d3.dgenies.y_zones[zone][1]) {
                    y_zone = d3.dgenies.mousetip.get_label(zone);
                    break;
                }
            }

            let html = "";

            if (match !== null) {
                html = `<strong>Query:</strong> ${match.y_zone}<br/>(${match.y_match[0]} - ${match.y_match[1]})<br/>
                        <strong>Target:</strong> ${match.x_zone}<br/>(${match.x_match[0]} - ${match.x_match[1]})<br/>
                        <strong>Identity:</strong> ${Math.round(match.idy * 100) / 100}`
            }
            else {
                html = `<table class="drawtooltip">
                    <tr>
                        <td class="tt-label">Query:</td><td>${y_zone}</td>
                    </tr>
                    <tr>
                        <td class="tt-label">Target:</td><td>${x_zone}</td>
                    </tr>
                    </table>`;
            }

            tip.html(html);

            let css = { top: mouseY, left: mouseX }

            if (match === null) {
                css.color = "#000";
                css.background = "#ededed";
            }
            else {
                let idy_class = "";
                if (match.idy >= 0.75) {
                    idy_class = "3";
                }
                else if (match.idy >= 0.5) {
                    idy_class = "2";
                }
                else if (match.idy >= 0.25) {
                    idy_class = "1";
                }
                else if (match.idy >= 0) {
                    idy_class = "0";
                }
                else {
                    idy_class = "-1"
                }
                css.background = d3.dgenies.color_idy[d3.dgenies.color_idy_theme]["palette"][idy_class];
                css.color = d3.dgenies.mousetip.getColorByBgColor(css.background)
            }

            if (!hidden && ((!e.ctrlKey && !d3.dgenies.zone_selected) || match !== null)) {
                tip.show().css(css);
            }

        }, 0);
    });
};


$.fn.mousetip_track_x = function (my_tip, relative_to = null, x = 20, y = 20) {
    let $this = $(this);
    console.log($this)
    let tip = relative_to === null ? $(my_tip, this) : $(my_tip, relative_to);
    let hidden = true;

    $this.hover(function (e) {
        if (!e.ctrlKey) {
            tip.show();
            hidden = false;
        }

    }, function () {
        hidden = true;
        tip.hide().removeAttr('style');

    }).mousemove(function (e) {

        tip.hide();

        window.setTimeout(() => {

            let rect = relative_to === null ? this.getBoundingClientRect() : $(relative_to)[0].getBoundingClientRect();
            let posX = rect.left + window.scrollX,
                posY = rect.top + window.scrollY,
                m_x = e.pageX - rect.left - window.scrollX,
                m_y = e.pageY - rect.top - window.scrollY;

            let mouseX = m_x + (x);
            let mouseY = m_y + (y);

            let match = d3.dgenies.mousetip.track_x.get_match(e);

            let html = "";
            if (match !== null) {
                html = `<strong>Target:</strong> ${match.contig}<br/>(${match.feature[0]} - ${match.feature[0] + match.feature[1]})<br/>
                        <strong>Value:</strong> ${match.feature[2]}<br/>
                        <strong>Comment:</strong> ${match.feature[3]}`
            }
            tip.html(html);
            let css = { top: mouseY, left: mouseX };

            if (!hidden && ((!e.ctrlKey && !d3.dgenies.zone_selected) || match !== null)) {
                tip.show().css(css);
            }

        }, 0);
    });
};


$.fn.mousetip_track_y = function(my_tip, relative_to = null, x = 20, y = 20) {
    let $this = $(this);
    console.log($this)
    let tip = relative_to === null ? $(my_tip, this) : $(my_tip, relative_to);
    let hidden = true;

    $this.hover(function (e) {
        if (!e.ctrlKey) {
            tip.show();
            hidden = false;
        }

    }, function () {
        hidden = true;
        tip.hide().removeAttr('style');

    }).mousemove(function (e) {

        tip.hide();

        window.setTimeout(() => {

            let rect = relative_to === null ? this.getBoundingClientRect() : $(relative_to)[0].getBoundingClientRect();
            let posX = rect.left + window.scrollX,
                posY = rect.top + window.scrollY,
                m_x = e.pageX - rect.left - window.scrollX,
                m_y = e.pageY - rect.top - window.scrollY;

            let mouseX = m_x + (x);
            let mouseY = m_y + (y);

            let match = d3.dgenies.mousetip.track_y.get_match(e);

            let html = "";
            if (match !== null) {
                html = `<strong>Query:</strong> ${match.contig}<br/>(${match.feature[0]} - ${match.feature[0] + match.feature[1]})<br/>
                        <strong>Value:</strong> ${match.feature[2]}<br/>
                        <strong>Comment:</strong> ${match.feature[3]}`
            }
            tip.html(html);
            let css = { top: mouseY, left: mouseX };

            if (!hidden && ((!e.ctrlKey && !d3.dgenies.zone_selected) || match !== null)) {
                tip.show().css(css);
            }

        }, 0);
    });
};


/**
 * Initialise tooltips
 */
d3.dgenies.mousetip.init = function () {
    d3.dgenies.mousetip.dotplot.init();
    d3.dgenies.mousetip.track_x.init();
    d3.dgenies.mousetip.track_y.init();
};

/**
 * Hide tooltips
 */
d3.dgenies.mousetip.hide = function () {
    $(".tip", "#draw").hide();
};

/**
 * get label to show
 *
 * @param {string} label initial label
 * @returns {string} new label
 */
d3.dgenies.mousetip.get_label = function (label) {
    if (label.startsWith("###MIX###")) {
        let parts = label.substr(10).split("###");
        label = "Mix:&nbsp;" + parts.slice(0, 3).join(",&nbsp;");
        if (parts.length > 3) {
            label += ",&nbsp;..."
        }
    }
    return label;
};

/**
 * Initialise tooltip for dotplot
 */
d3.dgenies.mousetip.dotplot.init = function () {
    $("#draw").append($("<span>").attr("class", "tip"));
    $("g.container").mousetip_dotplot(".tip", "#draw");
};


/**
 * Get match override by mouse cursor on dotplot
 *
 * @param e mouse event
 * @returns {{x_zone: string, y_zone: string, x_match: float[], y_match: float[], idy: float}}
 */
d3.dgenies.mousetip.dotplot.get_match = function(e) {
    let rect = $("g.container")[0].getBoundingClientRect();
    let posX = rect.left + window.scrollX,
        posY = rect.top + window.scrollY,
        width_c = rect.width,
        height_c = rect.height;
    let c_x = (e.pageX - posX) / width_c * d3.dgenies.scale,
        c_y = d3.dgenies.scale - ((e.pageY - posY) / height_c * d3.dgenies.scale);
    c_x = c_x / d3.dgenies.scale * d3.dgenies.x_len;
    c_y = c_y / d3.dgenies.scale * d3.dgenies.y_len;
    let error_x = d3.dgenies.content_lines_width / d3.dgenies.scale * d3.dgenies.x_len;
    let error_y = d3.dgenies.content_lines_width / d3.dgenies.scale * d3.dgenies.y_len;
    // let error_x = 0,
    //     error_y = 0;
    let match = null;
    let found = false;
    for (let i=3; i>=0; i--) {
        let j = 0;
        while(!found && j < d3.dgenies.lines[i].length) {
            let line = d3.dgenies.lines[i][j];
            let x_a = Math.min(line[0], line[1]);
            let x_b = Math.max(line[0], line[1]);
            let y_a = Math.min(line[2], line[3]);
            let y_b = Math.max(line[2], line[3]);
            if (x_a <= c_x && c_x <= x_b && y_a <= c_y && c_y <= y_b) {
                let m = (y_b - y_a) / (x_b - x_a);
                let p = y_a - (m * x_a);
                let y_xmouse = (m * c_x) + p;
                if (y_xmouse - error_y <= c_y && c_y <= y_xmouse + error_y) {
                    match = line;
                    found = true;
                }
            }
            j++;
        }
    }
    if (match !== null) {
        let y_zone = match[5];
        let x_zone = match[6];
        let y_min = null;
        let y_max = null;
        if (y_zone in d3.dgenies.y_zones) {
            let cy_min = d3.dgenies.y_zones[y_zone][0] / d3.dgenies.scale * d3.dgenies.y_len;
            y_min = d3.dgenies.get_human_readable_size(match[2] - cy_min, 3, "&nbsp;");
            y_max = d3.dgenies.get_human_readable_size(match[3] - cy_min, 3, "&nbsp;");
        }
        let x_min = null;
        let x_max = null;
        if (x_zone in d3.dgenies.x_zones) {
            let cx_min = d3.dgenies.x_zones[x_zone][0] / d3.dgenies.scale * d3.dgenies.x_len;
            x_min = d3.dgenies.get_human_readable_size(match[0] - cx_min, 3, "&nbsp;");
            x_max = d3.dgenies.get_human_readable_size(match[1] - cx_min, 3, "&nbsp;");
        }
        return {
            x_zone: x_zone,
            y_zone: y_zone,
            x_match: [x_min, x_max],
            y_match: [y_min, y_max],
            idy: match[4]
        }
    }
    return null;
}


/**
 * Initialise tooltip for dotplot
 */
d3.dgenies.mousetip.track_x.init = function () {
    $("svg.top-track").mousetip_track_x(".tip", "#draw");
};

/**
 * Get match override by mouse cursor on track x
 *
 * @param e mouse event
 * @returns {{x_zone: string, y_zone: string, x_match: float[], y_match: float[], idy: float}}
 */
d3.dgenies.mousetip.track_x.get_match = function (e) {
    // Get DOM object coordinates the mouse cursor is over.
    let rect = $("svg.top-track")[0].getBoundingClientRect();
    let posX = rect.left + window.scrollX,
        posY = rect.top + window.scrollY,
        width_c = rect.width,
        height_c = rect.height;
    console.log(posX, posY, width_c, height_c)

    // Transform into coordinates in data
    let c_x = (e.pageX - posX) / width_c * d3.dgenies.scale
    c_x = c_x / d3.dgenies.scale * d3.dgenies.x_len;

    let error_x = d3.dgenies.content_lines_width / d3.dgenies.scale * d3.dgenies.x_len;
    // let error_x = 0,

    let match = null;
    let found = false;
    let x_track = d3.dgenies.x_track.data;
    for (let x_id in x_track) {
        for (let feat of x_track[x_id]) {
            let f_start = feat[0];
            let f_len = feat[1];
            if (f_start <= c_x && c_x <= f_start + f_len) {
                match = { contig: x_id, feature: feat };
                found = true;
                break;
            }
        }
        if (found) { break; }
    }

    return match;
}


/**
 * Initialise tooltip for dotplot
 */
d3.dgenies.mousetip.track_y.init = function () {
    $("svg.right-track").mousetip_track_y(".tip", "#draw");
};

/**
 * Get match override by mouse cursor on track y
 *
 * @param e mouse event
 * @returns {{x_zone: string, y_zone: string, x_match: float[], y_match: float[], idy: float}}
 */
d3.dgenies.mousetip.track_y.get_match = function (e) {
    // Get DOM object coordinates the mouse cursor is over.
    let rect = $("svg.right-track")[0].getBoundingClientRect();
    let posX = rect.left + window.scrollX,
        posY = rect.top + window.scrollY,
        width_c = rect.width,
        height_c = rect.height;
    console.log(posX, posY, width_c, height_c)

    // Transform into coordinates in data
    let c_y = d3.dgenies.scale - ((e.pageY - posY) / height_c * d3.dgenies.scale);
    c_y = c_y / d3.dgenies.scale * d3.dgenies.y_len;

    let error_y = d3.dgenies.content_lines_width / d3.dgenies.scale * d3.dgenies.y_len;
    // let error_x = 0,

    let match = null;
    let found = false;
    let x_track = d3.dgenies.y_track.data;
    for (let x_id in x_track) {
        for (let feat of x_track[x_id]) {
            let f_start = feat[0];
            let f_len = feat[1];
            if (f_start <= c_y && c_y <= f_start + f_len) {
                match = { contig: x_id, feature: feat };
                found = true;
                break;
            }
        }
        if (found) { break; }
    }

    return match;
}
