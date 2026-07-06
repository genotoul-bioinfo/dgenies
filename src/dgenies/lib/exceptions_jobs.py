from .exceptions_core import DGeniesMessageException


class DGeniesJobCheckError(DGeniesMessageException):
    """
    Error appends on server side
    """

    def __init__(self, errors):
        """
        :param messages: errors messages produced during parsing
        :type messages: list of str
        """
        self._errors = errors

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return "Server error: " + self.__str__() + ". Please contact the support."

    def __str__(self):
        return "; ".join(self._errors)


class DGeniesRunError(DGeniesMessageException):

    def __init__(self, error: str):
        """
        :param messages: errors messages produced during parsing
        :type messages: list of str
        """
        self.error = error

    def __str__(self):
        return self.error


class DGeniesClusterRunError(DGeniesRunError):
    """
    Error appends during running job on cluster runner
    """
    pass


class DGeniesLocalRunError(DGeniesRunError):
    """
    Error appends during running job on local runner
    """
    pass


class DGeniesMissingParserError(DGeniesMessageException):

    def __init__(self, fmt):
        """
        :param messages: errors messages produced during parsing
        :type messages: list of str
        """
        self.fmt = fmt

    @property
    def message(self):
        """
        Get message for user

        :return: message for user
        :rtype: str
        """
        return self.__str__() + ". Please contact the support."

    def __str__(self):
        return "No parser found for format %s" % self.fmt


class DGeniesMissingJobError(DGeniesMessageException):

    def __str__(self):
        return "Job does not exists"


class DgeniesMissingSubjobsError(DGeniesMessageException):

    def __str__(self):
        return "Batch mode: no subjob found"


class DGeniesExampleNotAvailable(DGeniesMessageException):
    """
    Example file not available
    """
    pass


class DGeniesExampleInvalid(DGeniesMessageException):
    """
    Example file not valid
    """
    def __init__(self, name):
        """
        :param name: example name
        :type name: str
        :param clear_job: job must be cleaned when managing except if True, else not needed
        :type clear_job: bool
        """
        super().__init__()
        self.name = name

    def __str__(self):
        return "Invalid example: example://{}".format(self.name)


class DGeniesDeleteGalleryJobForbidden(DGeniesMessageException):

    def __str__(self):
        return "Deleting a job that is in gallery is forbidden"


class DGeniesValidationError(DGeniesMessageException):
    pass