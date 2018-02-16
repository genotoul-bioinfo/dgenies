if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.result = {};

// GLOBAL VARIABLES:
dgenies.result.id_res = null;

dgenies.result.init = function(id_res) {
    dgenies.result.id_res = id_res;
    d3.boxplot.init();
};

dgenies.result.remove_job_from_cookie = function(job) {
    let cookies = $.cookie("results");
    cookies = cookies !== undefined ? cookies.split("|") : [];
    let index = cookies.indexOf(job);
    let need_update = false;
    if (index > -1) {
        need_update = true;
        cookies.splice(index, 1);
    }
    $.cookie("results", cookies.join("|"), {path: '/'});
    if (need_update) {
        dgenies.update_results(cookies);
    }
};