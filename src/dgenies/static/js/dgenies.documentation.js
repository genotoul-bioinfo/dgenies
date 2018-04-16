if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.documentation = {};

dgenies.documentation.init = function () {
    $("table").addClass("table table-striped");
    dgenies.documentation.fix_links_headers();
};

dgenies.documentation.fix_links_headers = function() {
    $("#plan").on("click", "a", function (e) {
        e.preventDefault();
        dgenies.documentation.goto(this);
    })
};

dgenies.documentation.goto = function (elem) {
    let top = $($(elem).attr("href")).offset()["top"];
    $(window).scrollTop(top-55);
    $(elem).blur();
};