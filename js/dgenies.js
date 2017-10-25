dgenies = {}

dgenies.notify = function(text) {
    $.notify(text, {
        className: "warn",
        globalPosition: "top",
        position: "right",
        autoHideDelay: 10000
    })
}