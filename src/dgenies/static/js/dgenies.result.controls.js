if (!dgenies || !dgenies.result) {
    throw "dgenies.result wasn't included!"
}
dgenies.result.controls = {};

/**
 * Initialise controls of the result page
 */
dgenies.result.controls.init = function () {
    $("#sort-contigs").click(dgenies.result.controls.launch_sort_contigs);
    $("#hide-noise").click(dgenies.result.controls.launch_hide_noise);
    $("#summary").click(dgenies.result.controls.summary);
    $("#delete-job").click(dgenies.result.controls.delete_job);
    $("form#select-zone input.submit").click(dgenies.result.controls.select_zone);
    $("form#export select").change(dgenies.result.export.export);
};

/**
 * Build summary
 */
dgenies.result.controls.summary = function () {
    dgenies.show_loading("Building...");
    window.setTimeout(() => {
        dgenies.post(`/summary/${dgenies.result.id_res}`,
            {},
            function (data) {
                dgenies.hide_loading();
                if (data["success"]) {
                    if (data["status"] === "done") {
                        dgenies.result.summary.show(data["percents"]);
                    }
                    else if (data["status"] === "waiting") {
                        dgenies.result.controls.summary();
                    }
                }
                else {
                    dgenies.notify(data["message"] || "An error occurred! Please contact us to report the bug", "danger");
                }
            })
    }, 0);
};

/**
 * Build contigs sort
 */
dgenies.result.controls.launch_sort_contigs = function () {
    d3.boxplot.zoom.reset_scale();
    window.setTimeout(() => {
        dgenies.show_loading("Building...");
        window.setTimeout(() => {
            dgenies.post(`/sort/${dgenies.result.id_res}`,
                {},
                function (data) {
                    if (data["success"]) {
                        dgenies.reset_loading_message();
                        window.setTimeout(() => {
                            d3.boxplot.launch(data, true);
                        }, 0);
                    }
                    else {
                        dgenies.hide_loading();
                        dgenies.notify(data["message"] || "An error occurred! Please contact us to report the bug", "danger");
                    }
                }
            );
        }, 0);
    }, 0);
};

/**
 * Build reverse of a contig
 */
dgenies.result.controls.launch_reverse_contig = function () {
    if (d3.boxplot.query_selected !== null) {
        d3.boxplot.zoom.reset_scale();
        window.setTimeout(() => {
            dgenies.show_loading("Building...");
            window.setTimeout(() => {
                dgenies.post(`/reverse-contig/${dgenies.result.id_res}`,
                    {"contig": d3.boxplot.query_selected},
                    function (data) {
                        if (data["success"]) {
                            dgenies.reset_loading_message();
                            window.setTimeout(() => {
                                d3.boxplot.launch(data, true);
                            }, 0);
                        }
                        else {
                            dgenies.hide_loading();
                            dgenies.notify(data["message"] || "An error occurred! Please contact us to report the bug", "danger");
                        }
                    }
                );
            }, 0);
        }, 0);
    }
    else {
        dgenies.notify("Error: no query selected. Please contact us to report the bug", "danger");
    }
};

/**
 * Hide noise
 */
dgenies.result.controls.launch_hide_noise = function () {
    d3.boxplot.zoom.reset_scale();
    window.setTimeout(() => {
        dgenies.show_loading("Building...");
        window.setTimeout(() => {
            dgenies.post(`/freenoise/${dgenies.result.id_res}`,
                {noise: dgenies.noise ? 0 : 1},
                function (data) {
                    if (data["success"]) {
                        dgenies.noise = !dgenies.noise;
                        dgenies.reset_loading_message();
                        window.setTimeout(() => {
                            d3.boxplot.launch(data, true, true);
                        }, 0);
                    }
                    else {
                        dgenies.hide_loading();
                        dgenies.notify(data["message"] || "An error occurred! Please contact us to report the bug", "danger");
                    }
                }
            );
        }, 0);
    }, 0);
};

/**
 * Select zone with select boxes
 */
dgenies.result.controls.select_zone = function() {
    let contig_select = $("#select-contig").find(":selected");
    let target_select = $("#select-target").find(":selected");
    if (contig_select.val() !== "###NONE###" && target_select.val() !== "###NONE###") {
        d3.boxplot.select_zone(null, null, target_select.val(), contig_select.val(), true);
    }
    else {
        dgenies.notify("Please select zones into zoom!", "danger", 2000);
    }
};

/**
 * Delete current job (confirmed)
 */
dgenies.result.controls.do_delete_job = function () {
    dgenies.post(`/delete/${dgenies.result.id_res}`,
        {},
        function(data) {
            if (data["success"]) {
                dgenies.notify("Your job has been deleted!", "success", 1500);
                window.setTimeout(() => {
                    dgenies.result.remove_job_from_cookie(dgenies.result.id_res);
                    window.location = "/";
                }, 1500);
            }
            else {
                dgenies.notify("error" in data ? data["error"] : "An error has occurred. Please contact the support",
                    "danger")
            }
        })
};

/**
 * Ask confirm for delete current job
 */
dgenies.result.controls.delete_job = function () {
    let dialog = $("<div>")
        .attr("id", "dialog-confirm")
        .attr("title", "Delete job?");
    let icon = $("<span>")
        .attr("class", "ui-icon ui-icon-help")
        .css("float", "left")
        .css("margin", "12px 12px 20px 0");
    let body = $("<p>");
    body.append(icon);
    body.append("Confirm deletion of this job? This operation is definitive.");
    dialog.append(body);
    dialog.dialog({
        resizable: false,
        height: "auto",
        width: 500,
        modal: true,
        buttons: {
            "Yes": function() {
                $( this ).dialog( "close" );
                dgenies.result.controls.do_delete_job();
            },
            "No": function () {
                $( this ).dialog( "close" );
            }
        }
    });
};