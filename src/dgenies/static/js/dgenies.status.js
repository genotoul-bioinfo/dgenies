if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.status = {};


dgenies.status.init = function (status) {
    if (status !== "success" && status !== "done" && status !== "no-match" && status !== "fail") {
        dgenies.status.autoreload();
    }
};

dgenies.status.autoreload = function () {
    let get_p = new URLSearchParams(window.location.search);
    let refresh = get_p.get("refresh") !== null ? parseInt(get_p.get("refresh")) : 1;
    let count = get_p.get("count") !== null ? parseInt(get_p.get("count")) : 1;
    if (refresh < 30) {
        if (refresh % 5 === 0) {
            if (count > 3) {
                refresh += 1;
                count = 1;
            }
            else {
                count += 1
            }
        }
        else {
            refresh += 1
        }
    }
    setTimeout(function(){
        window.location.replace(`?refresh=${refresh}&count=${count}`);
    }, refresh * 1000)
};
