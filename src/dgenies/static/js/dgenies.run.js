if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.run = {};

// Init global variables:
dgenies.run.s_id = null;
dgenies.run.allowed_ext = [];
dgenies.run.max_upload_file_size = -1
dgenies.run.files = [undefined, undefined, undefined, undefined, undefined];
dgenies.run.allow_upload = false;
dgenies.run.ping_interval = null;
dgenies.run.target_example = "";
dgenies.run.query_example = "";
dgenies.run.tool_has_ava = {};
dgenies.run.enabled = true;

dgenies.run.init = function (s_id, allowed_ext, max_upload_file_size=1073741824, target_example="", query_example="",
                             tool_has_ava={}) {
    dgenies.run.s_id = s_id;
    dgenies.run.allowed_ext = allowed_ext;
    dgenies.run.max_upload_file_size = max_upload_file_size;
    dgenies.run.target_example = target_example;
    dgenies.run.query_example = query_example;
    dgenies.run.tool_has_ava = tool_has_ava;
    dgenies.run.restore_form();
    dgenies.run.set_events();
    dgenies.run.init_fileuploads();
};

dgenies.run.restore_form = function () {
    dgenies.run.change_fasta_type("query", $("select.query").find(":selected").text().toLowerCase(), true);
    dgenies.run.change_fasta_type("target", $("select.target").find(":selected").text().toLowerCase(), true);
    dgenies.run.change_fasta_type("queryidx", $("select.query").find(":selected").text().toLowerCase(), true);
    dgenies.run.change_fasta_type("targetidx", $("select.target").find(":selected").text().toLowerCase(), true);
};

dgenies.run.upload_next = function () {
    let next = dgenies.run.files.pop();
    while (next === undefined && dgenies.run.files.length > 0) {
        next = dgenies.run.files.pop();
    }
    if (next !== undefined) {
        next.submit();
        return true;
    }
    dgenies.run.do_submit();
    return false;
};

dgenies.run.__upload_server_error = function(fasta, data) {
    dgenies.notify("message" in data ? data["message"]: `An error has occured when uploading <b>${fasta}</b> file. Please contact us to report the bug!`,
                    "danger");
    dgenies.run.enable_form();
};

dgenies.run.allowed_file = function (filename) {
    return filename.indexOf('.') !== -1 &&
        (dgenies.run.allowed_ext.indexOf(filename.rsplit('.', 1)[1].toLowerCase()) !== -1 ||
            dgenies.run.allowed_ext.indexOf(filename.rsplit('.', 2).splice(1).join(".").toLowerCase()) !== -1);
};

dgenies.run._init_fileupload = function(fasta) {
    //TODO: factorise init_file_uploads
};

dgenies.run.init_fileuploads = function () {
    $('input.file-query').fileupload({
        dataType: 'json',
        formData: {
            "s_id": dgenies.run.s_id
        },
        add: function (e, data) {
            let filename = data.files[0].name;
            if (dgenies.run.allowed_file(filename))
                dgenies.run.files[0] = data;
            else {
                $("input.file-query").trigger("change"); // The value is null after fired
                dgenies.notify(`File <b>${filename}</b> is not supported!`, "danger", 3000)
            }
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            $('#progress-query').find('.bar').css(
                'width',
                progress + '%'
            );
        },
        success: function (data, success) {
            if (data["success"] !== "OK") {
                dgenies.run.__upload_server_error("query", data);
            }
            else if ("error" in data["files"][0]) {
                dgenies.run.add_error("Query file: " + data["files"][0]["error"], "error");
                dgenies.run.enable_form();
            }
            else {
                $("input#query").val(data["files"][0]["name"]);
                dgenies.run.hide_loading("query");
                dgenies.run.show_success("query");
                dgenies.run.upload_next();
            }
        },
        error: function (data, success) {
            dgenies.run.__upload_server_error("query", data);
        }
    });
    $('input.file-target').fileupload({
        dataType: 'json',
        formData: {
            "s_id": dgenies.run.s_id
        },
        add: function (e, data) {
            let filename = data.files[0].name
            if (dgenies.run.allowed_file(filename))
                dgenies.run.files[1] = data;
            else {
                $("input.file-target").trigger("change"); // The value is null after fired
                dgenies.notify(`File <b>${filename}</b> is not supported!`, "danger", 3000)
            }
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            $('#progress-target').find('.bar').css(
                'width',
                progress + '%'
            );
        },
        success: function (data, success) {
            if (data["success"] !== "OK") {
                dgenies.run.__upload_server_error("target", data);
            }
            else if ("error" in data["files"][0]) {
                dgenies.run.add_error("Target file: " + data["files"][0]["error"], "error");
                dgenies.run.enable_form();
            }
            else {
                $("input#target").val(data["files"][0]["name"]);
                dgenies.run.hide_loading("target");
                dgenies.run.show_success("target");
                dgenies.run.upload_next();
            }
        },
        error: function (data, success) {
            dgenies.run.__upload_server_error("target", data);
        }
    });

    //Trigger events on hidden file inputs:
    $("button#button-query").click(function() {
        $("input.file-query").trigger("click");
    })
    $("button#button-target").click(function() {
        $("input.file-target").trigger("click");
    })
};

dgenies.run.get_file_size_str = function(size) {
    if (size < 1000) {
        return size + " O";
    }
    else if (size < 1000000) {
        return Math.round(size / 1024) + " Ko";
    }
    else if (size < 1000000000) {
        return Math.round(size / 1048576) + " Mo";
    }
    return Math.round(size / 1073741824) + " Go";
};

dgenies.run.fill_examples = function () {
    $("select.target").val("1").trigger("change");
    $("input#target").val("example://" + dgenies.run.target_example);
    if (dgenies.run.query_example !== "") {
        $("select.query").val("1").trigger("change");
        $("input#query").val("example://" + dgenies.run.query_example);
    }
};

dgenies.run.set_events = function() {
    let max_file_size_txt = dgenies.run.get_file_size_str(dgenies.run.max_upload_file_size);
    $("input.file-query").change(function () {
        let file_size_query = $("div.file-size.query");
        if (this.files.length > 0)
            if (this.files[0].size <= dgenies.run.max_upload_file_size) {
                file_size_query.html(dgenies.run.get_file_size_str(this.files[0].size));
                dgenies.run.set_filename(this.files[0].name, "query");
            }
            else {
                $(this).val("");
                dgenies.run.set_filename("", "query");
                dgenies.notify(`File exceed the size limit (${max_file_size_txt})`, "danger", 2000);
                file_size_query.html("");
            }
        else {
            dgenies.run.set_filename("", "query");
            file_size_query.html("");
        }
    });

    $("input.file-target").change(function () {
        let file_size_target = $("div.file-size.target");
        if (this.files.length > 0) {
            if (this.files[0].size <= dgenies.run.max_upload_file_size) {
                file_size_target.html(dgenies.run.get_file_size_str(this.files[0].size));
                dgenies.run.set_filename(this.files[0].name, "target");
            }
            else {
                $(this).val("");
                dgenies.run.set_filename("", "target");
                dgenies.notify(`File exceed the size limit (${max_file_size_txt})`, "danger", 2000);
                file_size_target.html("");
            }
        }
        else {
            dgenies.run.set_filename("", "target");
            file_size_target.html("");
        }
    });

    $("button#submit").click(function () {
        dgenies.run.submit();
    });
    $("select.query").change(function() {
        dgenies.run.change_fasta_type("query", $("select.query").find(":selected").text().toLowerCase())
    });
    $("select.target").change(function() {
        dgenies.run.change_fasta_type("target", $("select.target").find(":selected").text().toLowerCase())
    });
    $("select.queryidx").change(function() {
        dgenies.run.change_fasta_type("queryidx", $("select.queryidx").find(":selected").text().toLowerCase())
    });
    $("select.targetidx").change(function() {
        dgenies.run.change_fasta_type("targetidx", $("select.targetidx").find(":selected").text().toLowerCase())
    });
    $("select.alignfile").change(function() {
        dgenies.run.change_fasta_type("alignfile", $("select.alignfile").find(":selected").text().toLowerCase())
    });
    $("button#example").click(function() {
        dgenies.run.fill_examples();
    });
    $("#tabs .tab").click(function() {
        dgenies.run.show_tab($(this).attr("id"));
    })
};

dgenies.run.show_tab = function(tab) {
    $(`#tabs #${tab}`).addClass("active");
    $(`#tabs .tab:not(#${tab})`).removeClass("active");
    $(`.tabx:not(${tab})`).hide();
    $(`.tabx.${tab}`).show();
};

dgenies.run.change_fasta_type = function (fasta, type, keep_url=false) {
    let button = $("button#button-" + fasta);
    let input = $("input#" + fasta);
    let container = $("div." + fasta + "-label");
    $("input.file-" + fasta).val("");
    if (type === "local") {
        button.show();
        input.prop("readonly", true);
        input.val("");
        container.width(300);
    }
    else {
        button.hide();
        input.prop("readonly", false);
        if (!keep_url)
            input.val("");
        container.width(348);
    }
    $("div.file-size." + fasta).html("");
};

dgenies.run.set_filename = function (name, fasta) {
    $("input#" + fasta).val(name);
};

dgenies.run.disable_form = function () {
    dgenies.run.enabled = false;
    $("input, select, button").prop("disabled", true);
};

dgenies.run.enable_form = function () {
    $('.progress').find('.bar').css(
        'width', '0%'
    );
    $("input, select, button").prop("disabled", false);
    $("div#uploading-loading").hide();
    $("button#submit").show();
    dgenies.run.hide_loading("query");
    dgenies.run.hide_loading("target");
    dgenies.run.hide_success("query");
    dgenies.run.hide_success("target");
    dgenies.run.files = [undefined, undefined];
    dgenies.run.restore_form();
    dgenies.run.enabled = true;
};

dgenies.run.do_submit = function () {
    $("div#uploading-loading").html("Submitting form...");
    dgenies.post("/launch_analysis",
        {
            "id_job": $("input#id_job").val(),
            "email": dgenies.mode === "webserver" ? $("input#email").val() : "",
            "query": $("input#query").val(),
            "query_type": $("select.query").find(":selected").text().toLowerCase(),
            "target": $("input#target").val(),
            "target_type": $("select.target").find(":selected").text().toLowerCase(),
            "s_id": dgenies.run.s_id,
            "tool": $("input[name=tool]:checked").val()
        },
        function (data, status) {
            if (data["success"]) {
                window.location = data["redirect"];
            }
            else {
                if (dgenies.run.ping_interval !== null) {
                    clearInterval(dgenies.run.ping_interval);
                    dgenies.run.ping_interval = null;
                }
                if ("errors" in data) {
                    for (let i = 0; i < data["errors"].length; i++) {
                        dgenies.notify(data["errors"][i], "danger", 3000);
                    }
                }
                else {
                    dgenies.notify("An error has occurred. Please contact the support", "danger", 3000);
                }
                dgenies.run.enable_form();
            }
        }
        );
};

dgenies.run.add_error = function (error) {
    $("div.errors-submit ul.flashes").append($("<li>").append(error));
};

dgenies.run.valid_form = function () {
    let has_errors = false;

    // Check name:
    if ($("input#id_job").val().length === 0) {
        $("label.id-job").addClass("error");
        dgenies.run.add_error("Name of your job is required!");
        has_errors = true;
    }

    // Check mail:
    if (dgenies.mode === "webserver") {
        let email = $("input#email").val();
        let mail_re = /^.+@.+\..+$/;
        if (email.match(mail_re) === null) {
            $("label.email").addClass("error");
            if (email === "")
                dgenies.run.add_error("Email is required!");
            else
                dgenies.run.add_error("Email is not correct!");
            has_errors = true;
        }
    }

    let tab = $("#tabs .tab.active").attr("id");

    /* TAB 1 */
    if (tab === "tab1") {
        //Check input target:
        if ($("input#target").val().length === 0) {
            $("label.file-target").addClass("error");
            dgenies.run.add_error("Target fasta is required!");
            has_errors = true;
        }

        //Check input query:
        let tool = $("input[name=tool]:checked").val();
        if (!dgenies.run.tool_has_ava[tool] && $("input#query").val().length === 0) {
            $("label.file-query").addClass("error");
            dgenies.run.add_error("Query fasta is required!");
            has_errors = true;
        }
    }

    /* TAB 2 */
    else {
        if ($("input#targetidx").val().length === 0) {
            $("label.file-targetidx").addClass("error");
            dgenies.run.add_error("Target file is required!");
            has_errors = true;
        }
        if ($("input#queryidx").val().length === 0) {
            $("label.file-queryidx").addClass("error");
            dgenies.run.add_error("Query file is required!");
            has_errors = true;
        }
        if ($("input#alignfile").val().length === 0) {
            $("label.file-align").addClass("error");
            dgenies.run.add_error("Alignment file is required!");
            has_errors = true;
        }
    }

    // Returns
    return !has_errors;
};

dgenies.run.show_loading = function(fasta) {
    $(".loading-file." + fasta).show();
};

dgenies.run.hide_loading = function(fasta) {
    $(".loading-file." + fasta).hide();
};

dgenies.run.show_success = function(fasta) {
    $(".upload-success." + fasta).show()
};

dgenies.run.hide_success = function(fasta) {
    $(".upload-success." + fasta).hide()
};

dgenies.run.reset_errors = function() {
    $("label").removeClass("error");
    $("div.errors-submit ul.flashes").find("li").remove();
};

dgenies.run.ask_for_upload = function () {
    console.log("Ask for upload...");
    dgenies.post("/ask-upload",
    {
        "s_id": dgenies.run.s_id
    },
    function (data, status) {
        if (data["success"]) {
            let allow_upload = data["allowed"];
            if (allow_upload) {
                $("div#uploading-loading").html("Uploading files...");
                dgenies.run.ping_interval = window.setInterval(dgenies.run.ping_upload, 15000);
                dgenies.run.upload_next();
            }
            else {
                window.setTimeout(dgenies.run.ask_for_upload, 15000);
            }
        }
        else {
            dgenies.notify("message" in data ? data["message"] : "An error has occurred. Please contact the support", "danger", 3000);
        }
    }, undefined, false
    );
};

dgenies.run.ping_upload = function () {
    dgenies.post("/ping-upload",
        {
            "s_id": dgenies.run.s_id
        },
        function (data, status) {
        }
    );
};

dgenies.run.check_url = function (url) {
    return url.startsWith("http://") || url.startsWith("https://") || url.startsWith("ftp://") ||
        url.startsWith("example://");
};

dgenies.run.reset_other_tab = function(tab) {
    if (tab === "tab1") {
        $("input#alignfile").val("");
        dgenies.run.files[2] = undefined;
        $("input#targetidx").val("");
        dgenies.run.files[3] = undefined;
        $("input#queryidx").val("");
        dgenies.run.files[4] = undefined;
    }
};

dgenies.run.start_uploads = function() {
    let tab = $("#tabs .tab.active").attr("id");
    let query_type = parseInt($("select.query").val());
    let has_uploads = false;
    let query_val = $("input#query").val();
    if (query_type === 0 && query_val.length > 0) {
        $("button#button-query").hide();
        dgenies.run.show_loading("query");
        has_uploads = true;
    }
    else {
        dgenies.run.files[0] = undefined;
        if (query_val !== "" && !dgenies.run.check_url(query_val)) {
            dgenies.run.add_error("Query file: invalid URL", "error");
            dgenies.run.enable_form();
            return false;
        }
    }
    let target_type = parseInt($("select.target").val());
    let target_val = $("input#target").val();
    if (target_type === 0 && target_val.length > 0) {
        $("button#button-target").hide();
        dgenies.run.show_loading("target");
        has_uploads = true;
    }
    else {
        dgenies.run.files[1] = undefined;
        if (target_val !== "" && !dgenies.run.check_url(target_val)) {
            dgenies.run.add_error("Target file: invalid URL", "error");
            dgenies.run.enable_form();
            return false;
        }
    }
    if (has_uploads) {
        $("div#uploading-loading").html("Asking for upload...");
        dgenies.run.ask_for_upload();
    }
    else {
        dgenies.run.upload_next();
    }
};

dgenies.run.show_global_loading = function () {
    $("button#submit").hide();
    $("button#example").hide();
    $("div#uploading-loading").show();
};

dgenies.run.submit = function () {
    dgenies.run.reset_errors();
    if (dgenies.run.valid_form()) {
        dgenies.run.disable_form();
        dgenies.run.show_global_loading();
        dgenies.run.start_uploads();
    }
};