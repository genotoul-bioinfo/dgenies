dgenies = {};
dgenies.loading = "#loading";
dgenies.login = null; // Username for websocket (anonymous)

dgenies.notify = function (text, type="warning", delay=5000) {
    $.notify({
        message: text
    },{
        type: type,
        placement: {
            from: "top",
            align: "center"
        },
        delay: delay,
        animate: {
            enter: 'animated fadeInDown',
            exit: 'animated fadeOutUp'
        },
        offset: 55,
        newest_on_top: true,
    })
};

dgenies.show_loading = function (message="Loading...", width=118) {
    $(dgenies.loading).find(".mylabel").html(message);
    $(dgenies.loading).find(".label").width(width);
    $(dgenies.loading).show();
    $(dgenies.loading).position({
        my: "center center",
        at: "center center",
        of: "#draw",
        collistion: "fit"
    });
};

dgenies.hide_loading = function () {
    $(dgenies.loading).hide();
    dgenies.reset_loading_message();
};

dgenies.set_loading_message = function (message) {
    $(dgenies.loading).find(".mylabel").html(message);
};

dgenies.reset_loading_message = function () {
    $(dgenies.loading).find(".mylabel").html("Loading...");
    $(dgenies.loading).find(".label").width(118);
};

dgenies.fill_select_zones = function(x_targets, y_contigs) {
    let select_contig = $("select#select-contig")
    select_contig.find("option[value!=0]").remove();
    for (let i=0; i< y_contigs.length; i++) {
        let label = y_contigs[i];
        if (label.startsWith("###MIX###")) {
            let parts = label.substr(10).split("###");
            label = "Mix: " + parts.slice(0, 3).join(", ");
            if (parts.length > 3) {
                label += ", ..."
            }
        }
        select_contig.append($('<option>', {
            value: i+1,
            text: label
        }))
    }
    select_contig.chosen({disable_search_threshold: 10});
    select_contig.trigger("chosen:updated")
    let select_target = $("select#select-target");
    select_target.find("option[value!=0]").remove();
    for (let i=0; i< x_targets.length; i++) {
        let label = x_targets[i];
        if (label.startsWith("###MIX###")) {
            let parts = label.substr(10).split("###");
            label = "Mix: " + parts.slice(0, 3).join(", ");
            if (parts.length > 3) {
                label += ", ..."
            }
        }
        select_target.append($('<option>', {
            value: i+1,
            text: label
        }))
    }
    select_target.chosen({disable_search_threshold: 10});
    select_target.trigger("chosen:updated")
};

dgenies.numberWithCommas = function(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};