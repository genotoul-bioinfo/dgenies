dgenies = {};
dgenies.loading = "#loading";

dgenies.notify = function (text, type="warn", delay=10000) {
    $.notify(text, {
        className: type,
        globalPosition: "top",
        position: "right",
        autoHideDelay: delay
    })
};

dgenies.show_loading = function () {
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
};

dgenies.fill_select_zones = function(x_targets, y_contigs) {
    let select_contig = $("select#select-contig")
    select_contig.find("option[value!=0]").remove();
    for (let i=0; i< y_contigs.length; i++) {
        select_contig.append($('<option>', {
            value: i+1,
            text: y_contigs[i]
        }))
    }
    select_contig.chosen({disable_search_threshold: 10});
    select_contig.trigger("chosen:updated")
    let select_target = $("select#select-target");
    select_target.find("option[value!=0]").remove();
    for (let i=0; i< x_targets.length; i++) {
        select_target.append($('<option>', {
            value: i+1,
            text: x_targets[i]
        }))
    }
    select_target.chosen({disable_search_threshold: 10});
    select_target.trigger("chosen:updated")
};

dgenies.numberWithCommas = function(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};