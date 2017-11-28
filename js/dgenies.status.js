if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.status = {};


dgenies.status.init = function (status) {
    if (status !== "success" && status !== "done" && status !== "no-match") {
        dgenies.status.autoreload();
    }
};

dgenies.status.autoreload = function () {
    setTimeout(function(){
        location.reload();
    }, 5000)
}