dgenies = {};
dgenies.loading = "#loading";
dgenies.noise = true;

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
    let select_contig = $("select#select-contig");
    select_contig.find("option[value!='###NONE###']").remove();
    for (let i=0; i< y_contigs.length; i++) {
        let label = y_contigs[i];
        let value = label;
        if (label.startsWith("###MIX###")) {
            let parts = label.substr(10).split("###");
            label = "Mix: " + parts.slice(0, 3).join(", ");
            if (parts.length > 3) {
                label += ", ..."
            }
        }
        select_contig.append($('<option>', {
            value: value,
            text: label
        }))
    }
    select_contig.chosen({disable_search_threshold: 10, search_contains: true});
    select_contig.trigger("chosen:updated");
    let select_target = $("select#select-target");
    select_target.find("option[value!='###NONE###']").remove();
    for (let i=0; i< x_targets.length; i++) {
        let label = x_targets[i];
        let value = label;
        if (label.startsWith("###MIX###")) {
            let parts = label.substr(10).split("###");
            label = "Mix: " + parts.slice(0, 3).join(", ");
            if (parts.length > 3) {
                label += ", ..."
            }
        }
        select_target.append($('<option>', {
            value: value,
            text: label
        }))
    }
    select_target.chosen({disable_search_threshold: 10, search_contains: true});
    select_target.trigger("chosen:updated")
};

dgenies.numberWithCommas = function(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};

dgenies.ajax = function(url, data, success, error, method="POST") {
    $.ajax(url,
        {
            method: method,
            data: data,
            success: success,
            error: error || function () {
                dgenies.hide_loading();
                dgenies.notify("An error occurred! Please contact us to report the bug", "danger");
            },
        }
    );
};

dgenies.post = function(url, data, success, error, async=true) {
    dgenies.ajax({
        url: url,
        data: data,
        success: success,
        error: error,
        type: "POST",
        async: async})
};

dgenies.get = function (url, data, success, error) {
    dgenies.ajax(url, data, success, error, "GET")
};