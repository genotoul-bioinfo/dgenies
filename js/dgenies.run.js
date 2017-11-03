if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.run = {};

// Init global variables:
dgenies.run.files = [undefined, undefined];

dgenies.run.init = function () {
    dgenies.run.restore_form();
    dgenies.run.set_events();
    dgenies.run.init_fileuploads();
};

dgenies.run.restore_form = function () {
    dgenies.run.change_fasta_type("query", $("select.query").find(":selected").text().toLowerCase(), true);
    dgenies.run.change_fasta_type("target", $("select.target").find(":selected").text().toLowerCase(), true);
};

dgenies.run.upload_next = function () {
    let next = dgenies.run.files.shift();
    while (next === undefined && dgenies.run.files.length > 0) {
        next = dgenies.run.files.shift();
    }
    if (next !== undefined) {
        next.submit();
        return true;
    }
    dgenies.run.do_submit();
    return false;
};

dgenies.run.init_fileuploads = function () {
    $('input.file-query').fileupload({
        dataType: 'json',
        add: function (e, data) {
            dgenies.run.files[0] = data;
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
                dgenies.notify("message" in data ? data["message"]: "An error has occured when uploading query file!",
                    "error");
                dgenies.run.enable_form();
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
        }
    });
    $('input.file-target').fileupload({
        dataType: 'json',
        formData: {folder: dgenies.run.upload_folder},
        add: function (e, data) {
            dgenies.run.files[1] = data;
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
                dgenies.notify("message" in data ? data["message"]: "An error has occured when uploading target file!",
                    "error");
                dgenies.run.enable_form();
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

dgenies.run.set_events = function() {
    $("input.file-query").change(function () {
        if (this.files.length > 0)
            dgenies.run.set_filename(this.files[0].name, "query");
        else
            dgenies.run.set_filename("", "query");
    });
    $("input.file-target").change(function () {
        if (this.files.length > 0)
            dgenies.run.set_filename(this.files[0].name, "target");
        else
            dgenies.run.set_filename("", "target");
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
};

dgenies.run.set_filename = function (name, fasta) {
    $("input#" + fasta).val(name);
};

dgenies.run.disable_form = function () {
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
    dgenies.run.hide_success("fasta");
    dgenies.run.files = [undefined, undefined];
    dgenies.run.restore_form();
};

dgenies.run.do_submit = function () {
    $("div#uploading-loading").html("Submitting form...");
    $.post("/launch_analysis",
        {
            "id_job": $("input#id_job").val(),
            "email": $("input#email").val(),
            "query": $("input#query").val(),
            "query_type": $("select.query").find(":selected").text().toLowerCase(),
            "target": $("input#target").val(),
            "target_type": $("select.target").find(":selected").text().toLowerCase()
        },
        function (data, status) {
            if (data["success"]) {
                window.location = data["redirect"];
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

    //Check input query:
    if ($("input#query").val().length === 0) {
        $("label.file-query").addClass("error");
        dgenies.run.add_error("Query fasta is required!");
        has_errors = true;
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

dgenies.run.start_uploads = function() {
    let query_type = parseInt($("select.query").val());
    if (query_type === 0) {
        $("button#button-query").hide();
        dgenies.run.show_loading("query");
    }
    else {
        dgenies.run.files[0] = undefined;
    }
    let target_type = parseInt($("select.target").val());
    if (target_type === 0 && $("input#target").val().length > 0) {
        $("button#button-target").hide();
        dgenies.run.show_loading("target");
    }
    else {
        dgenies.run.files[1] = undefined;
    }
    dgenies.run.upload_next();
};

dgenies.run.show_global_loading = function () {
    $("button#submit").hide();
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