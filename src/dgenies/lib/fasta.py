class Fasta:
    """
    Defines a fasta file: name of the sample, path to the fasta file, type of file (URL or local file), ...
    """

    def __init__(self, name, path, type_f, example=False):
        self._name = name
        self._path = path
        self._type = type_f
        self._example = example is not False

    def set_path(self, path):
        """
        Set path to the fasta file

        :param path: new path
        :type path: str
        """
        self._path = path

    def get_path(self):
        """
        Get path of the fasta file

        :return: fasta path
        :rtype: str
        """
        return self._path

    def set_name(self, name):
        """
        Set sample name

        :param name: new sample name
        :type name: str
        """
        self._name = name

    def get_name(self):
        """
        Get sample name

        :return: sample name
        :rtype: str
        """
        return self._name

    def get_type(self):
        """
        Get type: URL or local file

        :return: type
        :rtype: str
        """
        return self._type

    def is_example(self):
        """
        Return if current sample is an example data

        :return: current sample is an example data
        :rtype: bool
        """
        return self._example
