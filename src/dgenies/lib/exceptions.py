class DGeniesMessageException(Exception):
    """
    Exception with message for user.
    """

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__()

    @property
    def clear_job(self):
        return False


class DGeniesFileCheckError(DGeniesMessageException):
    """
    Exception raise when an error append while testing local files
    """

    def __init__(self, clear_job=False):
        """
        :param clear_job: job must be cleaned when managing except if True, else not needed
        :type clear_job: bool
        """
        self._clear_job = clear_job

    @property
    def clear_job(self):
        return self._clear_job


class DGeniesNotGzipFileError(DGeniesFileCheckError):
    """
    Exception raise when tested file is not a gzip file
    """

    def __init__(self, filename):
        """
        :param filename: name of the gzip file
        :type filename: str
        """
        super().__init__(clear_job=True)
        self.filename = filename

    def __str__(self):
        return "{} file is not a correct gzip file".format(self.filename)


class DGeniesUploadedFileSizeLimitError(DGeniesFileCheckError):
    """
    Exception raise when uploaded file are excess upload limit
    """

    def __init__(self, filename, sizelimit, unit="Mb", compressed=False):
        """
        :param filename: name of the file
        :type filename: str
        :param sizelimit: maximum allowed size for the file
        :type sizelimit: float
        :param unit: unit used for display
        :type unit: str
        :param compressed: size is compressed size if True, else uncompressed size
        :type compressed: boolean
        """
        super().__init__(clear_job=True)
        self.filename = filename
        self.sizelimit = sizelimit
        self.unit = unit
        self.compressed = compressed

    def __str__(self):
        return "{} file exceed size limit of {:d} {} ({}compressed)".format(self.filename, self.sizelimit, self.unit,
                                                                            '' if self.compressed else 'un')


class DGeniesAlignmentFileUnsupported(DGeniesFileCheckError):
    """
    Exception raise when alignment file format is not supported
    """

    def __init__(self):
        super().__init__()

    def __str__(self):
        return "Alignment file format not supported"


class DGeniesAlignmentFileInvalid(DGeniesFileCheckError):
    """
    Exception raise when alignment file content is invalid
    """

    def __init__(self):
        super().__init__()

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__() + ". Please check your file."

    def __str__(self):
        return "Alignment file is invalid"


class DGeniesIndexFileInvalid(DGeniesFileCheckError):
    """
    Exception raise index file content is invalid
    """

    def __init__(self, filename):
        super().__init__()
        self.filename = filename

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__() + ".  Please check your file."

    def __str__(self):
        return "{} index file is invalid".format(self.filename)


class DGeniesURLError(DGeniesMessageException):
    """
    Exception raise when an URL related error appends
    """

    def __init__(self, clear_job=False):
        """
        :param clear_job: job must be cleaned when managing except if True, else not needed
        :type clear_job: bool
        """
        self._clear_job = clear_job

    @property
    def clear_job(self):
        return self._clear_job

class DGeniesURLInvalid(DGeniesURLError):
    """
    Exception raise when URL is not connectable or contains an error
    """

    def __init__(self, url):
        """
        :param url: invalid url
        :type url: str
        """
        super().__init__()
        self.url = url

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return "<p>Url <b>{}</b> is not valid!</p>" \
               "<p>If this is unattended, please contact the support.</p>".format(self.url)

    def __str__(self):
        return "Url {} is not valid".format(self.url)


class DGeniesDistantFileTypeUnsupported(DGeniesURLError):
    """
    Exception raise when a distant file (from url) is unsupported
    """

    def __init__(self, filename, url, format_txt):
        """
        :param filename: name of the file
        :type filename: str
        :param url: url of the file
        :type url: str
        :param format_txt: text part about format of the file
        :type format_txt: str
        """
        super().__init__()
        self.filename = filename
        self.url = url
        self.format_txt = format_txt

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return "<p>File <b>{}</b> downloaded from <b>{}</b> is not {}!</p>" \
               "<p>If this is unattended, please contact the support.</p>".format(self.filename, self.url, self.format_txt)

    def __str__(self):
        return "File {} downloaded from {} is not {}!".format(self.filename, self.url, self.format_txt)


class DGeniesDownloadError(DGeniesMessageException):
    """
    Exception raised when something went wrong when downloading file
    """
    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__() + ". Please contact the support to report the bug."

    def __str__(self):
        return "Error while downloading input files"


class DGeniesBackupUnpackError(DGeniesMessageException):
    """
    Exception raised when something went wrong when unpacking backup file
    """
    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__() + ". If it is unattended, please contact the support."

    def __str__(self):
        return "Backup file is not valid"
