if (!d3 || !d3.boxplot) {
    throw "d3.boxplot wasn't included!"
}
d3.boxplot.mousetip = {};

$.fn.mousetip = function(my_tip, relative_to=null, x=20, y=20) {
    
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
    
    }).mousemove(function(e) {

        tip.hide();

        if (!e.ctrlKey && !d3.boxplot.zone_selected) {

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
                let x_g = (e.pageX - posX_g) / width_c * d3.boxplot.scale,
                    y_g = d3.boxplot.scale - ((e.pageY - posY_g) / height_c * d3.boxplot.scale);

                let x_zone = "unknown";
                for (let zone in d3.boxplot.x_zones) {
                    if (d3.boxplot.x_zones[zone][0] < x_g && x_g <= d3.boxplot.x_zones[zone][1]) {
                        x_zone = d3.boxplot.mousetip.get_label(zone);
                        break;
                    }
                }
                let y_zone = "unknown";
                for (let zone in d3.boxplot.y_zones) {
                    if (d3.boxplot.y_zones[zone][0] < y_g && y_g <= d3.boxplot.y_zones[zone][1]) {
                        y_zone = d3.boxplot.mousetip.get_label(zone);
                        break;
                    }
                }

                tip.html(`<table class="drawtooltip">
                        <tr>
                            <td class="tt-label">Query:</td><td>${y_zone}</td>
                        </tr>
                        <tr>
                            <td class="tt-label">Target:</td><td>${x_zone}</td>
                        </tr>
                      </table>`);

                if (!hidden) {
                    tip.show().css({

                        top: mouseY, left: mouseX

                    });
                }

            }, 0);

        }
    });
};

d3.boxplot.mousetip.init = function () {
    $("#draw").append($("<span>").attr("class", "tip"));
    $("g.container").mousetip(".tip", "#draw");
};

d3.boxplot.mousetip.hide = function () {
    $(".tip", "#draw").hide();
}

d3.boxplot.mousetip.get_label = function (label) {
    if (label.startsWith("###MIX###")) {
        let parts = label.substr(10).split("###");
        label = "Mix:&nbsp;" + parts.slice(0, 3).join(",&nbsp;");
        if (parts.length > 3) {
            label += ",&nbsp;..."
        }
    }
    return label;
}