class Fasta:
    def __init__(self, name, path, type_f):
        self.__name = name
        self.__path = path
        self.__type = type_f

    def set_path(self, path):
        self.__path = path

    def get_path(self):
        return self.__path

    def get_name(self):
        return self.__name

    def get_type(self):
        return self.__type
