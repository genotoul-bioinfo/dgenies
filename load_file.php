<?php

$paf = "test2/araduvseve2.paf";
$idx1 = "test2/evenia.idx";
$idx2 = "test2/Aradu.idx";
//$paf = "test3/2_10_vs_thal_f.paf";
//$idx1 = "test3/chloroplast_arabidopsis.idx";
//$idx2 = "test3/chloroplaste_2_10.idx";

$myfile = fopen($paf, "r") or die("Unable to open PAF file!");
$first_sample = null;
$second_sample = null;
$lines = array();
$len_x = 0;
$len_y = 0;
$min_idy = 1000000000;
$max_idy = -1000000000;
$scale = 1000; // Scale values
while (($line = fgets($myfile)) !== false) {
  $parts = explode("\t", $line);
	$v1 = $parts[0];
	$v6 = $parts[5];
	$ignore = false;
	$strand = $parts[4] == "+" ? 1 : -1;
	$idy = floatval($parts[9]) / floatval($parts[10]) * $strand;
	$min_idy = min($min_idy, $idy);
	$max_idy = max($max_idy, $idy);
	if (is_null($first_sample)) {
		$first_sample = $v1;
	}
	else if ($first_sample != $v1 || $v1 == $v6) {
		$ignore = true;
	}
	if (!$ignore) {
    $second_sample = $v6;
    $len_x = intval($parts[1]);
		$len_y = intval($parts[6]);
		//x1, x2, y1, y2, idy
		$x1 = intval($parts[2]);
		$x2 = intval($parts[3]);
		$y1 = intval($parts[$strand == 1 ? 7 : 8]);
		$y2 = intval($parts[$strand == 1 ? 8 : 7]);
        array_push($lines, [$x1, $x2, $y1, $y2, $idy]);
	}
}

fclose($myfile);

$myfile = fopen($idx1, "r") or die("Unable to open x_contigs file!");
$x_order = array();
$x_contigs = array();
while (($line = fgets($myfile)) !== false) {
  $parts = explode("\t", $line);
  $id = $parts[0];
  $len = intval($parts[1]);
  array_push($x_order, $id);
  $x_contigs[$id] = $len;
}
fclose($myfile);

$myfile = fopen($idx2, "r") or die("Unable to open y_contigs file!");
$y_order = array();
$y_contigs = array();
while (($line = fgets($myfile)) !== false) {
  $parts = explode("\t", $line);
  $id = $parts[0];
  $len = intval($parts[1]);
  array_push($y_order, $id);
  $y_contigs[$id] = $len;
}
fclose($myfile);

echo json_encode(array(
  'x_len' => $len_x,
  'y_len' => $len_y,
  'min_idy' => $min_idy,
  'max_idy' => $max_idy,
  'lines' => $lines,
  'x_contigs' => $x_contigs,
  'x_order' => $x_order,
  'y_contigs' => $y_contigs,
  'y_order' => $y_order,
  'name_x' => $first_sample,
  'name_y' => $second_sample
));

?>
