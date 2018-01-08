String.prototype.rsplit = function(sep, maxsplit) {
    let split = this.split(sep);
    return maxsplit ? [ split.slice(0, -maxsplit).join(sep) ].concat(split.slice(-maxsplit)) : split;
};