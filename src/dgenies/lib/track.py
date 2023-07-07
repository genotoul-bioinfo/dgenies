#!/usr/bin/env python3
import os
import re
from abc import ABC, abstractmethod
from typing import Union, Sequence
from dgenies.bin.index import Index
from dgenies.lib.exceptions import DGeniesMessageException, DGeniesFileDoesNotExist


class DGeniesUnknownTrackType(DGeniesMessageException):
    def __init__(self, error):
        super().__init__()


class DGeniesIncorrectTrackFileError(DGeniesMessageException):
    """
    Exception raise when trach file is Incorrectly formated
    """

    def __init__(self, error):
        super().__init__()
        self.error = error

    def __str__(self):
        return "Incorrect track file: {}".format(self.error)


class Track(ABC):
    """
    Functions applied to Track files
    """

    def __init__(self, track: str, idx: str, auto_parse: bool = True):
        """

        :param track: Bed file path
        :type track: str
        :param idx: seq index file path
        :param auto_parse: if True, parse PAF file at initialisation
        :type auto_parse: bool
        """
        self.track = track
        self.idx = idx
        self.contigs = {}
        self.data = dict()
        if auto_parse:
            self.parse_track()

    @abstractmethod
    def parse_track(self):
        pass

    @property
    @abstractmethod
    def type(self):
        pass

    @staticmethod
    def load(track: str, idx: str):
        data_dir = os.path.dirname(track)
        if os.path.exists(os.path.join(data_dir, ".sorted")) and os.path.exists(idx + ".sorted"):
            idx += ".sorted"
        if os.path.exists(track):
            with open(track, 'rt') as infile:
                track_path = infile.readline().rstrip('\n')
                if track_path.endswith(".bed"):
                    return Bed(track_path, idx)
                elif track_path.endswith(".wig"):
                    return Wiggle(track_path, idx)
                else:
                    raise DGeniesUnknownTrackType("Unknown track file type")
        else:
            return None

    def _parse_index(self):
        try:
            name, self.order, self.contigs, self.reversed, self.abs_start, length = Index.load(self.idx)
        except IOError:
            raise DGeniesFileDoesNotExist("Index file does not exist")

    def add_feature(self, chrom: str, start: int, length: int,
                    value: Union[int, str] = "", comment: str = ""):
        entry = (
            self.abs_start[chrom] + self.contigs[chrom] - (start + length) if self.reversed[chrom] \
                else self.abs_start[chrom] + start,  # start
            length,  # length
            value,  # value/color
            comment  # comment for tooltip
        )
        try:
            self.data[chrom].append(entry)
        except KeyError:
            self.data[chrom] = [entry]

    def get_d3js_data(self):
        return {
            "type": self.type,
            "data": self.data
        }


class Bed(Track):
    """
    Bed file specific functions
    """

    # Comment or blank line in bed file
    ignore_line_pattern = re.compile(r'^#|[ \t]+$')
    _type = "bed"

    def __init__(self, track: str, idx: str, auto_parse: bool = True):
        """

        :param track: Bed file path
        :type track: str
        :param idx: seq index file path
        :param auto_parse: if True, parse PAF file at initialisation
        :type auto_parse: bool
        """
        super().__init__(track, idx, auto_parse)

    @property
    def type(self):
        return self._type

    @staticmethod
    def rgb_to_hex(rgb: str) -> str:
        if rgb == "0":
            return '#000000'
        try:
            t_rgb = (int(x) for x in rgb.split(",")[0:3])
            return "#{:02X}{:02X}{:02X}".format(*t_rgb)
        except BaseException:
            raise DGeniesIncorrectTrackFileError("itemRbg={} is incorrect".format(rgb))

    def _add_feature(self, row):
        chrom = row[0]
        chrom_start = int(row[1])
        chrom_end = int(row[2])
        name = row[3] if len(row) >= 4 else None
        itemrgb = row[8] if len(row) >= 9 else None
        try:
            end = self.contigs[chrom]
            print(end, self.abs_start[chrom])
        except KeyError:
            # We skip unknown contigs (some may have been merged)
            pass
        else:
            if not (chrom_start < end):
                raise DGeniesIncorrectTrackFileError(
                    "'chromStart'={} overflows {} limits ({},{})".format(chrom_start, chrom, 0, end))
            if not (chrom_end < end):
                raise DGeniesIncorrectTrackFileError(
                    "'chromEnd'={} overflows {} limits ({},{})".format(chrom_end, chrom, 0, end))
            coord = (min(chrom_start, chrom_end), max(chrom_start, chrom_end))
            self.add_feature(
                chrom,
                coord[0],  # start
                coord[1] - coord[0],  # length
                self.rgb_to_hex(itemrgb) if itemrgb else "",  # value/color
                name if name else ""  # comment for tooltip
            )

    def parse_track(self):
        # Load index
        self._parse_index()

        # Load bed file
        try:
            with open(self.track, "rt") as infile:
                col_count = -1
                line_count = 0

                # Get first line of data (set column count)
                while col_count < 0:
                    line = infile.readline()
                    if line == "":
                        break
                    line = line.rstrip('\n')
                    line_count += 1
                    if not self.ignore_line_pattern.match(line):
                        row = re.split(r'[ \t]', line)
                        col_count = len(row)
                        if not (3 <= col_count <= 12):
                            raise DGeniesIncorrectTrackFileError("Invalid bed file")
                        self._add_feature(row)

                # Get remaining data from columns
                for line in infile.readlines():
                    line = line.rstrip('\n')
                    line_count += 1
                    if not self.ignore_line_pattern.match(line):
                        # data
                        row = re.split(r'[ \t]', line)
                        if len(row) != col_count:
                            raise DGeniesIncorrectTrackFileError("Invalid line: {}".format(line_count))
                        self._add_feature(row)
        except IOError:
            raise DGeniesFileDoesNotExist("Track file does not exist")


class Wiggle(Track):
    """
    Wiggle file specific functions
    """
    ignore_line_pattern = re.compile(r'^#')
    _type = "wig"

    def __init__(self, track: str, idx: str, auto_parse: bool = True):
        """

        :param track: Wiggle file path
        :type track: str
        :param idx: seq index file path
        :param auto_parse: if True, parse PAF file at initialisation
        :type auto_parse: bool
        """
        super().__init__(track, idx, auto_parse)

    @property
    def type(self):
        return self._type

    class VariableStep:
        def __init__(self, chrom: str, span: int = 1):
            self.chrom = chrom
            self.span = span

        def get_feature(self, data: Sequence[str]) -> list:
            start = int(data[0]) - 1
            value = float(data[1])
            res = [
                self.chrom,
                start,
                self.span,
                value,
                "{}".format(value)
            ]
            return res

    class FixStep:
        def __init__(self, chrom: str, start: int, step: int = 1, span: int = 1):
            self.chrom = chrom
            self.start = start - 1
            self.step = step
            self.span = span

        def get_feature(self, data: Sequence[str]) -> list:
            value = float(data[0])
            res = [
                self.chrom,
                self.start,
                self.span,
                value,
                "{}".format(value)]
            self.start += self.step
            return res

    def parse_track(self):
        # Load index
        self._parse_index()
        try:
            with open(self.track, "rt") as infile:
                add_step = None
                for line in infile.readlines():
                    line = line.rstrip('\n')

                    if line.startswith("track type="):
                        raise DGeniesIncorrectTrackFileError("Track type not supported in wiggle file")
                    if not self.ignore_line_pattern.match(line):
                        row = line.split()
                        if row[0] == "variableStep":
                            if len(row) < 2:
                                raise DGeniesIncorrectTrackFileError("Incorrect wiggle file")
                            d = {k: v for k, v in (tuple(e.split("=")) for e in row[1:])}
                            chrom = d["chrom"]
                            span = int(d.get("span", 1))
                            track_step = self.VariableStep(chrom, span)
                        elif row[0] == "fixedStep":
                            if len(row) < 4:
                                raise DGeniesIncorrectTrackFileError("Incorrect wiggle file")
                            d = {k: v for k, v in (tuple(e.split("=")) for e in row[1:])}
                            chrom = d["chrom"]
                            span = int(d.get("span", 1))
                            start = int(d["start"])
                            step = int(d["step"])
                            track_step = self.FixStep(chrom, start, span, step)
                        else:
                            # data
                            self.add_feature(*track_step.get_feature(row))
        except IOError:
            raise DGeniesFileDoesNotExist("Track file does not exist")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("bed")
    parser.add_argument("index")
    args = parser.parse_args()
    bed = Bed(args.bed, args.index)
    print(bed.data)
