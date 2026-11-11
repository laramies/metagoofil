import os

try:
    from urllib import request as urllib_request
except ImportError:  # Python 2 fallback
    import urllib2 as urllib_request


class downloader(object):
    def __init__(self, url, dir):
        self.url = url
        self.dir = dir
        self.filename = str(url.split("/")[-1])

    def down(self):
        target_path = os.path.join(self.dir, self.filename)
        if os.path.exists(target_path):
            return
        try:
            urllib_request.urlretrieve(self.url, target_path)
        except Exception:
            print("\t [x] Error downloading " + self.url)
            self.filename = ""

    def name(self):
        return self.filename
