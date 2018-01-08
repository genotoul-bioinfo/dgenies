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
