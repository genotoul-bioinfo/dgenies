class UploadFile:
    """
    Manage uploaded files
    """

    def __init__(self, name, type_f=None, size=None, not_allowed_msg=''):
        """

        :param name: File name
        :type name: str
        :param type_f: file MIME type
        :type type_f: str
        :param size: file size in bytes
        :type size: int
        :param not_allowed_msg: error to add for not allowed file
        :type not_allowed_msg: str
        """
        self.name = name
        self.type = type_f
        self.size = size
        self.not_allowed_msg = not_allowed_msg
        self.url = "data/%s" % name

    def get_file(self):
        """
        Get file object

        :return: file object
        :rtype: dict
        """
        if self.type is not None:
            # POST an image
            if self.type.startswith('image'):
                return {"name": self.name,
                        "type": self.type,
                        "size": self.size, 
                        "url": self.url}
            
            # POST a normal file
            elif self.not_allowed_msg == '':
                return {"name": self.name,
                        "type": self.type,
                        "size": self.size, 
                        "url": self.url}

            # File type is not allowed
            else:
                return {"error": self.not_allowed_msg,
                        "name": self.name,
                        "type": self.type,
                        "size": self.size}
        
        # GET normal file from disk
        else:
            return {"name": self.name,
                    "size": self.size, 
                    "url": self.url}
