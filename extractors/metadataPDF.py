#!/usr/bin/env python
#
# metadataPDF.py - dump pdf metadata 
#
# Copy of Yusuke's dumppdf to add dumpmeta
import sys, re
from pdfminer.psparser import PSKeyword, PSLiteral
from pdfminer.pdfparser import PDFDocument, PDFParser
from pdfminer.pdftypes import PDFStream, PDFObjRef, resolve1, stream_value


# dumpmeta
class metapdf:
	def __init__(self,fname, password=''):
		self.fname=fname
		self.password=password
		self.metadata=''
		self.users=[]
		self.software=[]
		self.paths=[]
		self.raw=""
		self.company=[]

	def getData(self):
		try:
			doc = PDFDocument()
			fp = file(self.fname, 'rb')
			parser = PDFParser(fp)
			parser.set_document(doc)
			doc.set_parser(parser)
			doc.initialize(self.password)
			metadata = resolve1(doc.catalog['Metadata'])
			parser.close()
			fp.close()
			for xref in doc.xrefs:
				info_ref=xref.trailer.get('Info')
				if info_ref:
					info=resolve1(info_ref)
				self.metadata=info
				self.raw = info
			return "ok"
		except:
			return "error"

	def getUsers(self):
		if self.metadata.has_key('Author'):
			self.users.append(self.metadata['Author'])
		return self.users

	def getCompany(self):
		if self.metadata.has_key('Company'):
			self.users.append(self.metadata['Company'])
		return self.company


	def getSoftware(self):
		if self.metadata.has_key('Producer'):
			self.software.append(self.metadata['Producer'])
		if self.metadata.has_key('Creator'):
			self.software.append(self.metadata['Creator'])
		return self.software

	def getPaths(self):
		return self.paths

	def getRaw(self):
		return self.raw
