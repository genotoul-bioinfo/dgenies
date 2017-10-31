if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.run = {};

// Init global variables:
dgenies.run.files = [];
dgenies.run.upload_folder = [];

dgenies.run.init = function () {
    dgenies.run.set_events();
    dgenies.run.init_fileuploads();
};

dgenies.run.init_fileuploads = function () {
    $('input.file-query').fileupload({
        dataType: 'json',
        formData: {folder: dgenies.run.upload_folder},
        add: function (e, data) {
            dgenies.run.files.push(data);
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            $('#progress-query').find('.bar').css(
                'width',
                progress + '%'
            );
        },
        success: function (data, success) {
            console.log(data);
            dgenies.run.upload_folder[0] = data["folder"];
            console.log(dgenies.run.upload_folder);
            if (dgenies.run.files.length > 0) {
                dgenies.run.files.shift().submit();
            }
        }
    });
    $('input.file-target').fileupload({
        dataType: 'json',
        formData: {folder: dgenies.run.upload_folder},
        add: function (e, data) {
            dgenies.run.files.push(data);
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            $('#progress-target').find('.bar').css(
                'width',
                progress + '%'
            );
        },
        success: function (data, success) {
            dgenies.run.upload_folder[0] = data["folder"];
            if (dgenies.run.files.length > 0) {
                dgenies.run.files.shift().submit();
            }
        }
    });
}

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
};

dgenies.run.set_filename = function (name, fasta) {
    $("input#" + fasta).val(name);
};

dgenies.run.submit = function () {
    console.log("submit!");
    $("div#progress-query").show();
    $("div#progress-target").show();

    if (dgenies.run.files.length > 0) {
        dgenies.run.files.shift().submit();
    }
};