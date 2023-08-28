if (!d3 || !d3.dgenies) {
    throw "d3.dgenies wasn't included!"
}
d3.dgenies.zoom = {};
d3.dgenies.zoom.help_timeout = null;

/**
 * Initialize zoom.init module
 */
d3.dgenies.zoom.init = function() {
    d3.dgenies.svgcontainer.on("click", d3.dgenies.zoom.click);
    d3.select(".drawcontainer")
        .on("mousedown", d3.dgenies.zoom.mousedown)
        .on("mouseup", d3.dgenies.zoom.mouseup)
        .on("mousemove", d3.dgenies.zoom.translate);
    d3.dgenies.svgcontainer.on("wheel", d3.dgenies.zoom.zoom);
};

/**
 * Click event action
 */
d3.dgenies.zoom.click = function () {
    if (!d3.event.ctrlKey && !d3.dgenies.all_disabled) {
        let cursor = d3.dgenies.zoom._cursor_pos();
        d3.dgenies.select_zone(cursor[0], cursor[1]);
    }
};

/**
 * Mousedown event action
 */
d3.dgenies.zoom.mousedown = function() {
    if (d3.dgenies.zoom_enabled) {
        d3.dgenies.mousetip.hide();
        let rect = $("g.container")[0].getBoundingClientRect();
        let posX = rect.left + window.scrollX,
            posY = rect.top + window.scrollY,
            width_c = rect.width,
            height_c = rect.height;
        let cursor_x = (d3.event.pageX - posX) / width_c * d3.dgenies.scale,
            cursor_y = (d3.event.pageY - posY) / height_c * d3.dgenies.scale;
        d3.dgenies.translate_start = [cursor_x, cursor_y];
        d3.dgenies.posX = posX;
        d3.dgenies.posY = posY;
        let old_transform = d3.dgenies.container.attr("transform");
        d3.dgenies.old_translate = [0, 0];
        if (old_transform !== null) {
            let search_tr = old_transform.match(/translate\(([-\d.]+),\s*([-\d.]+)\)/);
            d3.dgenies.old_translate = [parseFloat(search_tr[1]), parseFloat(search_tr[2])];
        }
    }
};

/**
 * Mouseup event action
 */
d3.dgenies.zoom.mouseup = function() {
    d3.dgenies.translate_start = null;
    $("#help-trans").fadeOut("slow");
};

/**
 * Translate event action
 */
d3.dgenies.zoom.translate = function () {
    let rect = $("g.container")[0].getBoundingClientRect();
    let posX = d3.dgenies.posX,
        posY = d3.dgenies.posY,
        width_c = rect.width,
        height_c = rect.height;
    let cursor_x = (d3.event.pageX - posX) / width_c * d3.dgenies.scale,
        cursor_y = (d3.event.pageY - posY) / height_c * d3.dgenies.scale;
    if (d3.dgenies.translate_start !== null && d3.event.ctrlKey) {
        let old_transform = d3.dgenies.container.attr("transform");
        //let scale = 1;
        let scale_x = 1;
        let scale_y = 1;
        if (old_transform) {
            let scale = old_transform.match(/scale\(([-\d.]+)(,\s*([-\d.]+))?\)/);
            scale_x = scale[1];
            scale_y = scale[1];
            if (scale[3] !== undefined)
                scale_y = scale[3];
        }
        let translate = [d3.dgenies.old_translate[0] + (cursor_x - d3.dgenies.translate_start[0]) * scale_x,
                         d3.dgenies.old_translate[1] + (cursor_y - d3.dgenies.translate_start[1]) * scale_y];
        let min_tr = [d3.dgenies.scale - 0.2 * d3.dgenies.scale, d3.dgenies.scale - 0.2 * d3.dgenies.scale];
        let max_tr = [-d3.dgenies.scale * scale_x + 200, -d3.dgenies.scale * scale_x + 200];
        if (translate[0] < max_tr[0]) {
            translate[0] = max_tr[0];
        }
        else if (translate[0] > min_tr[0]) {
            translate[0] = min_tr[0];
        }
        if (translate[1] < max_tr[1]) {
            translate[1] = max_tr[1];
        }
        else if (translate[1] > min_tr[1]) {
            translate[1] = min_tr[1];
        }
        let new_transform = `scale(${scale_x}, ${scale_y})translate(${translate[0]/scale_x}, ${translate[1]/scale_y}) `;
        d3.dgenies.container.attr("transform", new_transform);

        if (translate[0] !== 0 || translate[1] !== 0) {
            $("#restore-all").prop("disabled", false);
        }
        else {
            $("#restore-all").prop("disabled", true);
        }

        //Update axis:
        d3.dgenies.draw_top_axis();
        d3.dgenies.draw_right_axis();
        d3.dgenies.zoom_bottom_axis();
        d3.dgenies.zoom_left_axis();
        
        //Update tracks:
        d3.dgenies.zoom_top_track();
        d3.dgenies.zoom_right_track();
    }
    else if(d3.dgenies.translate_start !== null) {
        let help_trans = $("#help-trans");
        help_trans.fadeIn("slow");
    }
};

/**
 * Get cursor position
 *
 * @param {DOMRect} rect if given, dont get it from DOM
 * @returns {*[]} x and y position, plus the container rect object at third position
 * @private
 */
d3.dgenies.zoom._cursor_pos = function(rect=null) {
    let event = d3.event;
    if (rect === null) {
        rect = $("g.container")[0].getBoundingClientRect();
    }
    let posX = rect.left + window.scrollX,
        posY = rect.top + window.scrollY,
        width_c = rect.width,
        height_c = rect.height;
    let x = (event.pageX - posX) / width_c * d3.dgenies.scale,
        y = d3.dgenies.scale - ((event.pageY - posY) / height_c * d3.dgenies.scale);
    return [x, y, rect];
};

/**
 * Zoom stuff
 */
d3.dgenies.zoom.zoom = function () {
    if (d3.event.ctrlKey) {
        d3.event.preventDefault();
        d3.dgenies.mousetip.hide();
        if (d3.dgenies.zoom_enabled) {
            let cursor = d3.dgenies.zoom._cursor_pos();
            let zoom_f = 1.2;
            let old_transform = d3.dgenies.container.attr("transform");
            if (old_transform !== null) {
                let search_tr = old_transform.match(/translate\(([-\de.]+),\s*([-\de.]+)\)/);
                let search_sc = old_transform.match(/scale\(([-\de.]+)(,\s*[-\de.]+)?\)/);
                old_transform = {
                    "scale": parseFloat(search_sc[1]),
                    "translate": [parseFloat(search_tr[1]), parseFloat(search_tr[2])]
                }
            }
            else {
                old_transform = {
                    "scale": 1,
                    "translate": [0, 0]
                }
            }
            let new_scale;
            let new_rect = cursor[2];
            if (d3.event.deltaY < 0) {
                new_scale = old_transform["scale"] * zoom_f;
                new_rect["width"] *= zoom_f;
                new_rect["height"] *= zoom_f;
            }
            else {
                new_scale = old_transform["scale"] / zoom_f;
                let scale_ratio = zoom_f;
                if (new_scale < 1) {
                    new_scale = 1;
                    scale_ratio = old_transform["scale"]
                }
                new_rect["width"] /= scale_ratio;
                new_rect["height"] /= scale_ratio;
            }

            new_rect["bottom"] = new_rect["y"] + new_rect["height"];
            new_rect["right"] = new_rect["x"] + new_rect["width"];

            let new_cursor = d3.dgenies.zoom._cursor_pos(new_rect);
            let x_trans = (new_cursor[0] - cursor[0]) * new_scale;
            let y_trans = (new_cursor[1] - cursor[1]) * new_scale;
            let translate_x = old_transform["translate"][0]+x_trans;
            let translate_y = old_transform["translate"][1]-y_trans;

            let new_transform = `translate(${translate_x},${translate_y}) scale(${new_scale})`;
            d3.dgenies.container.attr("transform", new_transform);
            d3.dgenies.zoom_scale_lines = new_scale;

            d3.dgenies.zoom._cursor_pos();

            //Correct lines stroke width to be not impacted by the zoom:
            d3.selectAll("path.content-lines").attr("stroke-width", d3.dgenies.content_lines_width / new_scale);
            d3.selectAll("line.break-lines").attr("stroke-width", d3.dgenies.break_lines_width / new_scale);

            //Update axis:
            d3.dgenies.draw_top_axis();
            d3.dgenies.draw_right_axis();
            d3.dgenies.zoom_bottom_axis();
            d3.dgenies.zoom_left_axis();
            d3.dgenies.zoom_top_track(new_scale);
            d3.dgenies.zoom_right_track(new_scale);

            if ((translate_x <= 0.00001 && translate_x >= -0.00001) &&
                (translate_y <= 0.00001 && translate_y >= -0.00001) && new_scale === 1) {
                $("#restore-all").prop("disabled", true);
            }
            else {
                $("#restore-all").prop("disabled", false);
            }
        }
    }
    else if (d3.dgenies.zoom_enabled) {
        let help_zoom = $("#help-zoom");
        help_zoom.fadeIn("slow");
        if (d3.dgenies.zoom.help_timeout !== null) {
            window.clearTimeout(d3.dgenies.zoom.help_timeout);
        }
        d3.dgenies.zoom.help_timeout = window.setTimeout(() => {
            help_zoom.fadeOut("slow");
        }, 700);
    }
};

/**
 * Restore previous scale
 *
 * @param transform: transform object
 */
d3.dgenies.zoom.restore_scale = function(transform) {
    if (d3.dgenies.zone_selected) {
        d3.dgenies.select_zone(null, null, d3.dgenies.zone_selected[0], d3.dgenies.zone_selected[1], true)
    }
    else {
        let scale_x = 1;
        let scale_y = 1;
        if (transform !== null) {
            let search_sc = transform.match(/scale\(([-\de.]+)(,\s*[-\de.]+)?\)/);
            scale_x = search_sc[1];
            scale_y = search_sc[2];
        }
        else {
            transform = "translate(0,0)scale(1,1)";
        }
        if (scale_y === undefined) {
            scale_y = 1000000;
        }
        d3.dgenies.container.attr("transform", transform);
        d3.selectAll("path.content-lines").attr("stroke-width", d3.dgenies.content_lines_width / Math.min(scale_x, scale_y));
        if (d3.dgenies.break_lines_show) {
            d3.selectAll("line.break-lines").style("visibility", "visible");
            d3.selectAll("line.break-lines").attr("stroke-width", d3.dgenies.break_lines_width);
        }
    }
};

/**
 * Reset scale
 *
 * @param {boolean} temp if true, reset it temporarily
 * @param {function} after function to launch after staff
 * @param {boolean} force do it even if events are disabled
 * @returns {boolean} true if done, else false
 */
d3.dgenies.zoom.reset_scale = function (temp=false, after=null, force=true) {
    if (!d3.dgenies.all_disabled || force) {
        dgenies.show_loading();
        window.setTimeout(() => {
            //Reset scale:
            d3.dgenies.container.attr("transform", "scale(1,1)translate(0,0)");
            d3.dgenies.zoom_scale_lines = 1;

            //Restore lines stroke width:
            d3.selectAll("path.content-lines").attr("stroke-width", d3.dgenies.content_lines_width);
            if (d3.dgenies.break_lines_show) {
                d3.selectAll("line.break-lines").style("visibility", "visible");
                d3.selectAll("line.break-lines").attr("stroke-width", d3.dgenies.break_lines_width);
            }

            //Update left and bottom axis:
            d3.dgenies.draw_left_axis(d3.dgenies.y_len);
            d3.dgenies.draw_bottom_axis(d3.dgenies.x_len);

            //Update top and right axis:
            d3.dgenies.draw_top_axis();
            d3.dgenies.draw_right_axis();

            //Update tracks:
            d3.dgenies.zoom_right_track();
            d3.dgenies.zoom_top_track();

            if (!temp)
                d3.dgenies.zone_selected = false;

            dgenies.hide_loading();

            //Re-enable zoom:
            d3.dgenies.zoom_enabled = true;

            if (after !== null) {
                after();
            }
        }, 0);
        return true
    }
    return false
    //
    // //Restore axis:
    // d3.dgenies.draw_left_axis(d3.dgenies.y_len);
    // d3.dgenies.draw_bottom_axis(d3.dgenies.x_len);
    // d3.dgenies.draw_top_axis(d3.dgenies.x_zones);
    // d3.dgenies.draw_right_axis(d3.dgenies.y_zones);
    //
    // d3.selectAll("line.content-lines").remove();
    // d3.dgenies.draw_lines(d3.dgenies.lines, d3.dgenies.x_len, d3.dgenies.y_len);

    // dgenies.show_loading();
    // window.setTimeout(() => {
    //     d3.select("g.container").html(d3.dgenies.full_pict);
    //     dgenies.hide_loading();
    // }, 0);
};