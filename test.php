<html>
<head>
	<script src="igenocomp/js/jquery-3.2.1.min.js" type="text/JavaScript"></script>
	<script src="igenocomp/js/jquery-ui.min.js" type="text/JavaScript"></script>
	<script src="igenocomp/js/sprintf.min.js" type="text/JavaScript"></script>
	<script src="igenocomp/js/d3.min.js" type="text/JavaScript"></script>
	<script src="igenocomp/js/draw_graph.js" type="text/JavaScript"></script>
	<link rel="stylesheet" href="igenocomp/css/jquery-ui.min.css" type="text/css">
	<link rel="stylesheet" href="igenocomp/css/style.css" type="text/css">
</head>
<body onload="d3.boxplot.init();">
<div id="subdraw">
    <div id="draw"></div>
    <div id="loading">
    <div class="cssload-container">
        <div class="cssload-whirlpool"></div>
    </div>
    <div class="label">
        <div class="mylabel">
            Loading...
        </div>
    </div>
</div>
</div>
<div id="legend">
<div class="title">
Legend
</div>
<div class="draw">
</div>
</body>
</html>
