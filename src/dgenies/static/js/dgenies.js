dgenies = {};
dgenies.loading = "#loading";
dgenies.noise = true;
dgenies.mode = "webserver";

/**
 * Initialise dgenies client app
 *
 * @param {array} all_jobs list of user jobs (in standalone mode, empty in other modes)
 * @param {string} mode server mode (standalone or webserver)
 */
dgenies.init = function(all_jobs, mode) {
    dgenies.mode = mode;
    let cookies = $.cookie("results");
    let cookie_wall = $.cookie("wall");
    if (mode === "webserver") {
        if (cookie_wall === undefined) {
            $("#cwall").modal({
              escapeClose: false,
              clickClose: false,
              showClose: false
            });
        }
        cookies = (cookies !== undefined && cookies.length > 0) ? cookies.split("|") : [];
    }
    else {
        cookies = all_jobs;
        dgenies.save_cookies(cookies);
    }
    dgenies.update_results(cookies);
};

/**
 * Save cookie on the browser
 * @param {array} cookies list of jobs
 */
dgenies.save_cookies = function(cookies) {
    $.cookie("results", cookies.join("|"), {path: '/'});
};

dgenies.accept_cookie_wall = function(){
    $.cookie("wall", '', { expires: 180, path: '/' });
}

/**
 * Update list of jobs
 * @param {array} results: new list of jobs
 */
dgenies.update_results = function(results) {
    let job_list_item = $("ul.nav li.result ul");
    job_list_item.html("");
    if (results.length > 0) {
        for (let i=0; i<results.length; i++) {
            let result = results[i];
            job_list_item.append($("<li>").append($("<a>")
            .addClass("dropdown-item")
            .attr("href", `/result/${result}`)
            .text(result)));
        }
    }
    else {
        job_list_item.append($("<li>").append($("<a>")
            .addClass("dropdown-item")
            .attr("href", "/run")
            .text("Please run a job!")))
    }
};

/**
 * Show new notification
 *
 * @param {string} text notification text
 * @param {string} type notification type (danger, warning, info, success) according to Bootstrap Notify library
 * @param {int} delay time before hide notification
 */
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

/**
 * Show loading popup
 *
 * @param {string} message loading message
 * @param {int} width popup width
 */
dgenies.show_loading = function (message="Loading...", width=118) {
    $("input,form#export select").prop("disabled", true);
    d3.dgenies.all_disabled = true;
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

/**
 * Hide loading popup
 */
dgenies.hide_loading = function () {
    $("input,form#export select").prop("disabled", false);
    d3.dgenies.all_disabled = false;
    $(dgenies.loading).hide();
    dgenies.reset_loading_message();
};

/**
 * Change loading message on current popup
 *
 * @param {string} message new message
 */
dgenies.set_loading_message = function (message) {
    $(dgenies.loading).find(".mylabel").html(message);
};

/**
 * Reset loading message to its default value
 */
dgenies.reset_loading_message = function () {
    $(dgenies.loading).find(".mylabel").html("Loading...");
    $(dgenies.loading).find(".label").width(118);
};

/**
 * Fill list of zones on select boxes (contigs and chromosomes)
 *
 * @param {array} x_targets list of chromosomes of target
 * @param {array} y_contigs list of contigs of query
 */
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

/**
 * Show human readable number higher than 1000: 1000 -> 1,000
 *
 * @param {int} x number
 * @returns {string} human readable number
 */
dgenies.numberWithCommas = function(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};

/**
 * Ajax server call
 *
 * @param url url to call
 * @param data data to send
 * @param success success function
 * @param error error function
 * @param method method (GET, POST, ...)
 */
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

/**
 * Post server call
 *
 * @param url url to call
 * @param data data to send
 * @param success success function
 * @param error error function
 * @param async make call asynchronous
 */
dgenies.post = function(url, data, success, error, async=true) {
    dgenies.ajax({
        url: url,
        data: data,
        success: success,
        error: error,
        type: "POST",
        async: async})
};

/**
 * Get server call
 *
 * @param url url to call
 * @param data data to send
 * @param success success function
 * @param error error function
 */
dgenies.get = function (url, data, success, error) {
    dgenies.ajax(url, data, success, error, "GET")
};