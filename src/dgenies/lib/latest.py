import requests
import json
import os
import threading
from dgenies.config_reader import AppConfigReader


class Latest:

    def __init__(self):
        self.latest = ""
        self.win32 = ""
        config = AppConfigReader()
        self._save_latest = os.path.join(config.config_dir, ".latest")
        self.load()

    def load(self):
        if os.path.exists(self._save_latest):
            with open(self._save_latest, "r") as latest_f:
                self.latest = latest_f.readline().rstrip()
                self.win32 = latest_f.readline().rstrip()
            if self.latest == "" or self.win32 == "":
                self.update()
            else:
                self.update_async()
        else:
            self.update()

    def update_async(self):
        thread = threading.Timer(1, self.update)
        thread.start()

    def update(self):
        try:
            call = requests.get("https://api.github.com/repos/genotoul-bioinfo/dgenies/releases/latest")
            if call.ok:
                release = json.loads(call.content.decode("utf-8"))
                if "tag_name" in release:
                    self.latest = release["tag_name"][1:]
                    for asset in release["assets"]:
                        if asset["name"].endswith(".exe"):
                            self.win32 = asset["browser_download_url"]
                            break
        except ConnectionError:
            pass
        else:
            self._write_update()

    def _write_update(self):
        if self.latest != "" or self.win32 != "":
            with open(self._save_latest, "w") as latest_f:
                latest_f.write("\n".join([self.latest, self.win32]))
