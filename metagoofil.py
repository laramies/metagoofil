from discovery import googlesearch
from extractors import *
import urllib
import os
import downloader
import processor
import sys
import getopt
import markup 
import warnings
warnings.filterwarnings("ignore") # To prevent errors from hachoir deprecated functions, need to fix.

print "\n*************************************"
print "* Metagoofil Ver 2.0 - Reborn       *"
print "* Christian Martorella		    *"
print "* Edge-Security.com                 *"
print "* cmartorella_at_edge-security.com  *"
print "* BACKTRACK 5 Edition!!             *"
print "*************************************"

def usage():
	print "Metagoofil 2.0:\n"
	print "Usage: metagoofil options\n"
	print "		-d: domain to search"
	print "		-t: filetype to download (pdf,doc,xls,ppt,odp,ods,docx,xlsx,pptx)"
	print "		-l: limit of results to search (default 200)"
	print "		-h: work with documents in directory (use \"yes\" for local analysis)"
	print "		-n: limit of files to download"
	print "		-o: working directory" 
	print "		-f: output file\n"
	print "Examples:"
	print "  metagoofil.py -d microsoft.com -t doc,pdf -l 200 -n 50 -o microsoftfiles -f results.html"
	print "  metagoofil.py -h yes -o microsoftfiles -f results.html (local dir analysis)\n"
	sys.exit()


global limit,filelimit,start,password,all,localanalysis,dir
limit=100
filelimit=50
start=0
password=""
all=[]
dir="test"

def writehtml(users,softs,paths,allinfo,fname,dir):
	page = markup.page()
	page.init (title="Metagoofil Results",css=('edge.css'),footer="Edge-security 2011")
	page.h2("Metagoofil results")
	page.h3("User names found:")
	page.ul( class_="userslist")
	page.li( users, class_="useritem")
	page.ul.close( )
	page.h3("Software versions found:")
	page.ul( class_="softlist")
	page.li(softs, class_="softitem")
	page.ul.close( )
	page.h3("Servers and paths found:")
	if paths!=[]:
		page.ul( class_="pathslist")
		page.li(paths, class_="pathitem")
		page.ul.close( )
	page.h3("Files analyzed:")
	page.ul( class_="files")
	for x in allinfo:
		page.li(x[0], class_="file")
	page.ul.close()
	page.h2("Files and metadata found:")
	for x in allinfo:
		page.h3(x[0])
		page.a("Local copy", class_="link", href=dir+"/"+x[0])
		page.pre(style="background:#C11B17;border:1px solid;")
		page.pre(x[1])
		page.pre(x[3])
		page.pre.close()
	file = open(fname,'w')
	for x in page.content:
		try:
			file.write(x)
		except:
			#print "Exception" +  x # send to logs
			pass
	file.close
	return "ok"


def doprocess(argv):
	localanalysis= "no"
	if len(sys.argv) < 3:
		usage()
	try:
		opts,args = getopt.getopt(argv,"l:d:f:h:n:t:o:")
	except getopt.GetoptError:
		usage()
	for opt,arg in opts:
		if opt == '-d':
			word = arg
		elif opt == '-t':
			filetypes=[]
			if arg.count(",") != 0:
				filetypes = arg.split(",")
			else:
				filetypes.append(arg)
				print filetypes
		elif opt == '-l':
			limit = int(arg)
		elif opt == '-h':
			localanalysis=arg
		elif opt == '-n':
			filelimit = int(arg)
		elif opt == '-o':
			dir = arg
		elif opt == '-f':
			outhtml = arg
	if os.path.exists(dir):
		pass
	else:
		os.mkdir(dir)
	if localanalysis == "no":
		print "[-] Starting online search..."
		for filetype in filetypes:
			print "\n[-] Searching for "+filetype+ " files, with a limit of " + str(limit)
			search=googlesearch.search_google(word,limit,start,filetype)
			search.process_files()
			files=search.get_files()
			print "Results: " + str(len(files)) + " files found" 
			print "Starting to download "+ str(filelimit) + " of them.."
			print "----------------------------------------------------\n"
			counter=0
			for x in files:
				if counter <= filelimit:
					print "["+str(counter)+"/"+str(filelimit)+"] " + x
					getfile=downloader.downloader(x,dir)
					getfile.down()
					filename=getfile.name()	
					if filename !="":
						if filetype == "pdf":
							test=metadataPDF.metapdf(dir+"/"+filename,password)
						elif filetype == "doc" or filetype == "ppt" or filetype == "xls":
							test=metadataMSOffice.metaMs2k(dir+"/"+filename)	
							if os.name=="posix":
								testex=metadataExtractor.metaExtractor(dir+"/"+filename)
						elif filetype == "docx" or filetype == "pptx" or filetype == "xlsx":
							test=metadataMSOfficeXML.metaInfoMS(dir+"/"+filename)
						res=test.getData()
						if res=="ok":
							raw=test.getRaw()
							users=test.getUsers()
							paths=test.getPaths()
							soft=test.getSoftware()
							if (filetype == "doc" or filetype == "xls" or filetype == "ppt") and os.name=="posix":
								testex.runExtract()
								testex.getData()
								paths.extend(testex.getPaths())
							respack=[x,users,paths,soft,raw]
							all.append(respack)
						else:
							print "error" #A error in the parsing process
					else:
						print "pass"
					counter+=1
	else:
		print "[-] Starting local analysis in directory " + dir
		dirList=os.listdir(dir)
		for filename in dirList:
			if filename !="":
				filetype=str(filename.split(".")[-1])
				if filetype == "pdf":
					test=metadataPDF.metapdf(dir+"/"+filename,password)
				elif filetype == "doc" or filetype == "ppt" or filetype == "xls":
					test=metadataMSOffice.metaMs2k(dir+"/"+filename)
					if os.name=="posix":
						testex=metadataExtractor.metaExtractor(dir+"/"+filename)
				elif filetype == "docx" or filetype == "pptx" or filetype == "xlsx":
					test=metadataMSOfficeXML.metaInfoMS(dir+"/"+filename)
				res=test.getData()
				if res=="ok":
					raw=test.getRaw()
					users=test.getUsers()
					paths=test.getPaths()
					soft=test.getSoftware()
					if (filetype == "doc" or filetype == "xls" or filetype == "ppt") and os.name=="posix":
						valid=testex.runExtract()
						if valid=="ok":
							testex.getData()
							paths.extend(testex.getPaths())
						else:
							pass
					soft=test.getSoftware()
					raw=test.getRaw()
					respack=[filename,users,paths,soft,raw]
				else:
					pass #An error in the parsing process
			else:
				pass
			all.append(respack)

	proc=processor.processor(all)
	userlist=proc.sort_users()
	softlist=proc.sort_software()
	pathlist=proc.sort_paths()
	try:
		save = writehtml(userlist,softlist,pathlist,all,outhtml,dir)
	except:
		print "Error creating the file"
	print "\n[+] List of users found:"
	print "--------------------"
	for x in  userlist:
		print x
	print "\n[+] List of software found:"
	print "-----------------------"
	for x in softlist:
		print x
	print "\n[+] List of paths and servers found:"
	print "--------------------------------"
	for x in pathlist:
		print x

if __name__ == "__main__":
	try: doprocess(sys.argv[1:])
	except KeyboardInterrupt:
		print "Process interrupted by user."
	except:
		sys.exit()
