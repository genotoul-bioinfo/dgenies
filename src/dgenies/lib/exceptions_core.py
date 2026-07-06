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


class DGeniesUnknownOptionError(DGeniesMessageException):
    """
    Exception raise when an unknown option is used
    """

    def __init__(self, key):
        super().__init__()
        self.key = key

    def __str__(self):
        return "Option unavailable: {}".format(self.key)


class DGeniesUnknownToolError(DGeniesMessageException):
    """
    Exception raise when an unknown tool is used
    """

    def __init__(self, key):
        super().__init__()
        self.key = key

    def __str__(self):
        return "Tool unavailable: {}".format(self.key)


