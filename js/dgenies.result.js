if (!dgenies) {
    throw "dgenies wasn't included!"
}
dgenies.result = {};

dgenies.result.init = function(id_res) {
    dgenies.result.socketio(id_res);
};

dgenies.result.socketio = function (id_res) {
    // Connect to Websocket:
    let socket = io.connect();
    socket.on('connect', function() {
        socket.emit('join', {room: "res_" + id_res});
    });
    socket.on("connected", function(data) {
        console.log("Websocket connection established");
        if ("username" in data) {
            dgenies.login = data["username"];
        }
    });

    /*
     * Websocket events
     */

    /**
     * Update the dotplot
     */
    socket.on('update_graph', function(data){
        if ("success" in data && data["success"]) {
            console.log("Update graph");
            dgenies.show_loading();
            window.setTimeout(() => {
                d3.boxplot.launch(data, true);
            }, 0);
        }
    });
};