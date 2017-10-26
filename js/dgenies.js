dgenies = {};
dgenies.loading = "#loading";

dgenies.notify = function (text) {
    $.notify(text, {
        className: "warn",
        globalPosition: "top",
        position: "right",
        autoHideDelay: 10000
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
}