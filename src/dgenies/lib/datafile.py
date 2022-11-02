class DataFile:
    """
    Defines a data file: name of the sample, path to the data file, type of file (URL or local file), ...
    """

    def __init__(self, name, path, type_f, example=False):
        """

        :param name: sample name
        :type name: str
        :param path: data file path
        :type path: str
        :param type_f: type of file (local file or URL)
        :type type_f: str
        :param example: is an example job
        :type example: bool
        """
        self._name = name
        self._path = path
        self._type = type_f
        self._example = example is not False

    def set_path(self, path):
        """
        Set path to the data file

        :param path: new path
        :type path: str
        """
        self._path = path

    def get_path(self):
        """
        Get path of the data file

        :return: data path
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

    def set_type(self, f_type):
        """
        Set file type

        :param f_type: type of file (local file or URL)
        :type f_type: str
        """
        self._type = f_type

    def is_example(self):
        """
        Return if current sample is an example data

        :return: current sample is an example data
        :rtype: bool
        """
        return self._example

    def clone(self):
        return DataFile(name=self._name, path=self._path, type_f=self._type, example=self._example)

    @staticmethod
    def create(name: str, path: str):
        """
        Create Datafile from a path, url, example

        :param name: sample name
        :type name: str
        :param path: data file path
        :type path: str
        """
        type_f = 'local'
        if path.startswith("ftp://") or path.startswith("http://") or path.startswith("https://"):
            type_f = 'URL'
        example = path.startswith("example://")
        return DataFile(name=name, path=path, type_f=type_f, example=example)
