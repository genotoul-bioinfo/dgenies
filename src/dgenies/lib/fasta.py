class Fasta:
    def __init__(self, name, path, type_f, example=False):
        self._name = name
        self._path = path
        self._type = type_f
        self._example = example

    def set_path(self, path):
        self._path = path

    def get_path(self):
        return self._path

    def set_name(self, name):
        self._name = name

    def get_name(self):
        return self._name

    def get_type(self):
        return self._type

    def is_example(self):
        return self._example
