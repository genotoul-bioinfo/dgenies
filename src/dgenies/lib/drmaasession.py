import drmaa
from .decorators import Singleton

@Singleton
class DrmaaSession:

    def __init__(self):
        self.session = drmaa.Session()
        self.session.initialize()

    def exit(self):
        print("Exiting DRMAA...")
        self.session.exit()
