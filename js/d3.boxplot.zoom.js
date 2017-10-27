if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.zoom = {};

d3.boxplot.zoom.init = function() {
    d3.boxplot.svgcontainer.on("click", d3.boxplot.zoom.click);
    d3.select(".drawcontainer")
        .on("mousedown", d3.boxplot.zoom.mousedown)
        .on("mouseup", d3.boxplot.zoom.mouseup)
        .on("mousemove", d3.boxplot.zoom.translate);
    d3.boxplot.svgcontainer.on("wheel", d3.boxplot.zoom.zoom);
};

// d3.boxplot.zoom.zoom = function () {
//     console.log(d3.event);
//     if (d3.event.ctrlKey) {
//         d3.event.preventDefault();
//         let rect = $("g.container")[0].getBoundingClientRect();
//         let posX = rect.left,
//             posY = rect.top,
//             width_c = rect.width,
//             height_c = rect.height;
//         let cursor_x = (d3.event.pageX - posX) / width_c * d3.boxplot.x_len,
//             cursor_y = (d3.event.pageY - posY) / height_c * d3.boxplot.y_len;
//         console.log(cursor_x, cursor_y);
//         let zoom_f = 1.2;
//         let old_transform = d3.boxplot.container.attr("transform")
//         if (old_transform !== null) {
//             let search_tr = old_transform.match(/translate\(([-\de.]+),([-\de.]+)\)/);
//             let search_sc = old_transform.match(/scale\(([-\de.]+)(,[-\de.]+)?\)/);
//             old_transform = {
//                 "scale": parseFloat(search_sc[1]),
//                 "translate": [parseFloat(search_tr[1]), parseFloat(search_tr[2])]
//             }
//         }
//         else {
//             old_transform = {
//                 "scale": 1,
//                 "translate": [0, 0]
//             }
//         }
//         console.log(old_transform);
//
//         //Cursor localisation on picture with old zoom:
//         let cursor_old = [(cursor_x - old_transform["translate"][0]), (cursor_y - old_transform["translate"][1])]; //x0,y0 bleu (visible)
//         console.log([(cursor_x - old_transform["translate"][0]), (cursor_y - old_transform["translate"][1])]);
//         console.log("c_old", cursor_old);
//         let new_scale,
//             cursor_new;
//         if (d3.event.deltaY < 0) {
//             new_scale = old_transform["scale"] * zoom_f;
//             cursor_new = [cursor_old[0] * zoom_f, cursor_old[1] * zoom_f];
//         }
//         else {
//             new_scale = old_transform["scale"] / zoom_f;
//             if (new_scale < 1) {
//                 new_scale = 1;
//                 zoom_f = old_transform["scale"] / new_scale;
//             }
//             cursor_new = [cursor_old[0] / zoom_f, cursor_old[1] / zoom_f];
//         }
//
//         let new_transform = vsprintf("translate(%f,%f) scale(%f)",
//             [old_transform["translate"][0] - (cursor_new[0] - cursor_old[0]),
//              old_transform["translate"][1] - (cursor_new[1] - cursor_old[1]),
//              new_scale]);
//         d3.boxplot.container.attr("transform", new_transform);
//
//         //Correct lines stroke width to be not impacted by the zoom:
//         d3.selectAll("line.content-lines").attr("stroke-width", (d3.boxplot.x_len / 400) / new_scale);
//     }
// };

d3.boxplot.zoom.click = function () {
    if (!d3.event.ctrlKey) {
        let event = d3.event;
        let rect = $("g.container")[0].getBoundingClientRect();
        let posX = rect.left + window.scrollX,
            posY = rect.top + window.scrollY,
            width_c = rect.width,
            height_c = rect.height;
        let x = (event.pageX - posX) / width_c * d3.boxplot.scale,
            y = d3.boxplot.scale - ((event.pageY - posY) / height_c * d3.boxplot.scale);
        d3.boxplot.select_zone(x, y);
    }
};

d3.boxplot.zoom.mousedown = function() {
    if (d3.boxplot.zoom_enabled) {
        d3.boxplot.mousetip.hide();
        let rect = $("g.container")[0].getBoundingClientRect();
        let posX = rect.left + window.scrollX,
            posY = rect.top + window.scrollY,
            width_c = rect.width,
            height_c = rect.height;
        let cursor_x = (d3.event.pageX - posX) / width_c * d3.boxplot.scale,
            cursor_y = (d3.event.pageY - posY) / height_c * d3.boxplot.scale;
        d3.boxplot.translate_start = [cursor_x, cursor_y];
        d3.boxplot.posX = posX;
        d3.boxplot.posY = posY;
        let old_transform = d3.boxplot.container.attr("transform");
        d3.boxplot.old_translate = [0, 0];
        if (old_transform !== null) {
            let search_tr = old_transform.match(/translate\(([-\d.]+),\s*([-\d.]+)\)/);
            d3.boxplot.old_translate = [parseFloat(search_tr[1]), parseFloat(search_tr[2])];
        }
    }
};

d3.boxplot.zoom.mouseup = function() {
    d3.boxplot.translate_start = null;
};

d3.boxplot.zoom.translate = function () {
    let rect = $("g.container")[0].getBoundingClientRect();
    let posX = d3.boxplot.posX,
        posY = d3.boxplot.posY,
        width_c = rect.width,
        height_c = rect.height;
    let cursor_x = (d3.event.pageX - posX) / width_c * d3.boxplot.scale,
        cursor_y = (d3.event.pageY - posY) / height_c * d3.boxplot.scale;
    if (d3.boxplot.translate_start !== null && d3.event.ctrlKey) {
        let old_transform = d3.boxplot.container.attr("transform");
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
        let translate = [d3.boxplot.old_translate[0] + (cursor_x - d3.boxplot.translate_start[0]) * scale_x,
                         d3.boxplot.old_translate[1] + (cursor_y - d3.boxplot.translate_start[1]) * scale_y];
        let min_tr = [d3.boxplot.scale - 0.2 * d3.boxplot.scale, d3.boxplot.scale - 0.2 * d3.boxplot.scale];
        let max_tr = [-d3.boxplot.scale * scale_x + 200, -d3.boxplot.scale * scale_x + 200];
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
        let new_transform = `translate(${translate[0]}, ${translate[1]}) scale(${scale_x}, ${scale_y})`;
        d3.boxplot.container.attr("transform", new_transform);

        //Update axis:
        d3.boxplot.draw_top_axis();
        d3.boxplot.draw_right_axis();
        d3.boxplot.zoom_bottom_axis();
        d3.boxplot.zoom_left_axis();
    }
};


d3.boxplot.zoom.zoom = function () {
    if (d3.event.ctrlKey) {
        d3.event.preventDefault();
        d3.boxplot.mousetip.hide();
        if (d3.boxplot.zoom_enabled) {
            let zoom_f = 1.2;
            let old_transform = d3.boxplot.container.attr("transform");
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
            if (d3.event.deltaY < 0) {
                new_scale = old_transform["scale"] * zoom_f;
            }
            else {
                new_scale = old_transform["scale"] / zoom_f;
                if (new_scale < 1) {
                    new_scale = 1;
                }
            }
            let new_transform = `translate(${old_transform["translate"][0]},${old_transform["translate"][1]}) 
            scale(${new_scale})`;
            d3.boxplot.container.attr("transform", new_transform);
            d3.boxplot.zoom_scale_lines = new_scale;

            //Correct lines stroke width to be not impacted by the zoom:
            d3.selectAll("path.content-lines").attr("stroke-width", d3.boxplot.content_lines_width / new_scale);
            d3.selectAll("line.break-lines").attr("stroke-width", d3.boxplot.break_lines_width / new_scale);

            //Update axis:
            d3.boxplot.draw_top_axis();
            d3.boxplot.draw_right_axis();
            d3.boxplot.zoom_bottom_axis();
            d3.boxplot.zoom_left_axis();
        }
    }
};