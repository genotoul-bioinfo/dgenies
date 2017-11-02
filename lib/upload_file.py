class UploadFile:
    def __init__(self, name, type_f=None, size=None, not_allowed_msg=''):
        self.name = name
        self.type = type_f
        self.size = size
        self.not_allowed_msg = not_allowed_msg
        self.url = "data/%s" % name

    def get_file(self):
        if self.type is not None:
            # POST an image
            if self.type.startswith('image'):
                return {"name": self.name,
                        "type": self.type,
                        "size": self.size, 
                        "url": self.url}
            
            # POST an normal file
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
