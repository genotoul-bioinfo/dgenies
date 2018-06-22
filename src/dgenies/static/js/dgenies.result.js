if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.result = {};

// GLOBAL VARIABLES:
dgenies.result.id_res = null;

/**
 * Initialise app for result app
 *
 * @param {string} id_res job id
 */
dgenies.result.init = function(id_res) {
    dgenies.result.id_res = id_res;
    dgenies.result.add_to_list();
    d3.boxplot.init();
};

/**
 * Update list of results from cookie
 */
dgenies.result.add_to_list = function () {
    let cookies = $.cookie("results");
    cookies = cookies !== undefined ? cookies.split("|") : [];
    if (cookies.indexOf(dgenies.result.id_res) === -1) {
        cookies.splice(0, 0, dgenies.result.id_res);
        dgenies.save_cookies(cookies);
        dgenies.update_results(cookies);
    }
};

/**
 * Remove a job in cookie
 * @param {string} job job id to remove
 */
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