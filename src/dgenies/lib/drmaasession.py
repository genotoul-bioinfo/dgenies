try:
    import drmaa
except:
    print("Error: unable to import DRMAA module")
from .decorators import Singleton

@Singleton
class DrmaaSession:
    """
    Initialize and close a DRMAA session (for job submission to a cluster)
    """

    def __init__(self):
        self.session = drmaa.Session()
        self.session.initialize()

    def exit(self):
        print("Exiting DRMAA...")
        self.session.exit()
