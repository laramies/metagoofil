import urllib, os

class downloader():
	def __init__(self,url,dir):
		self.url=url
		self.dir=dir
		self.filename=str(url.split("/")[-1])

	def down(self):
		if os.path.exists(self.dir+"/"+self.filename):
			pass
		else:
			try:
				urllib.urlretrieve(self.url,self.dir+"/"+self.filename)		
			except:
				print "Error downloading " + self.url
				self.filename=""
	def name(self):
		return self.filename
