import time
import re
import fnmatch
from xml.dom.minidom import parse
from xml.dom.minidom import getDOMImplementation
import binascii
import os

import_ok = True

try:
	import weechat #@UnresolvedImport
except:
	print("This script must be run under WeeChat.")
	print("Get WeeChat now at: http://www.weechat.org/")
	import_ok = False

SCRIPT_NAME    = "DarkTowerAdFilter"
SCRIPT_AUTHOR  = "ruuk"
SCRIPT_VERSION = "0.0.1"
SCRIPT_LICENSE = "GPL2"
SCRIPT_DESC    = "Filter For Channel Server Ads"

SAVEPATH = None
			
class xmlFunctions:
	def startNewXml(self):
		impl = getDOMImplementation()
		self.dom = impl.createDocument(None,'main',None)
		
	def startLoadXml(self,path=''):
		if not path: path = self.path
		if not path: return self.startNewXml()
		try: self.dom = parse(path)
		except: return self.startNewXml()
	
	def setPath(self,path):
		self.path = path
		
	def saveXml(self,path=''):
		if not path: path = self.path
		if not path: path = os.path.join(SAVEPATH,self.name + '.xml')
		fi = open(path,'w')
		fi.write(self.dom.toxml('utf-8'))
		fi.close()
		
	def saveDict(self,data):
		self.startNewXml()
		for d in data:
			self.addElement(d,data=data[d])
		self.saveXml()
		self.end()
		
	def loadDict(self):
		valdict = {}
		self.startLoadXml()
		for e in self.dom.documentElement.getElementsByTagName('entry'):
			key = e.getElementsByTagName('key')
			data = e.getElementsByTagName('data')
			val = ''
			c = key[0].childNodes
			if c:
				tag = c[0].data
			c = data[0].childNodes
			if c:
				val = c[0].data
			val = binascii.unhexlify(val)
			try:
				if '.' in val: val = float(val)
				else: val = int(val)
			except:
				pass
			if tag: valdict[binascii.unhexlify(tag)] = val
		self.end()
		return valdict
		
	def addElement(self,tag,element=None,data=None):
		pe = self.dom.createElement('entry')
		if element: element.appendChild(pe)
		else: self.dom.documentElement.appendChild(pe)
		tag = binascii.hexlify(str(tag))
		if data: data = binascii.hexlify(str(data))
		keynode = self.dom.createElement('key')
		datanode = self.dom.createElement('data')
		pe.appendChild(keynode)
		pe.appendChild(datanode)
		keynode.appendChild(self.dom.createTextNode(tag))
		datanode.appendChild(self.dom.createTextNode(data))
		return pe
		
	
	def end(self):
		self.dom.unlink()
		
class DTChannelAd():
	def __init__(self,nick,network):
		nickAtNetwork = nick + "@" + network
		self.data = {}
		self.xdccLast = 0
		self.xdccTemplate = ''
		self.set('lastTime',0)
		self.set('nickAtNet',nickAtNetwork)
		self.set('network',network)
		self.set('nick',nick)
		self.nickAtNet = nickAtNetwork
		self.xml = xmlFunctions()
		self.xml.setPath(os.path.join(SAVEPATH,nickAtNetwork + '.xml'))

	def set(self,name,value): #@ReservedAssignment
		self.data[name.lower()] = value
		if not value: del self.data[name.lower()]

	def get(self,name):
		name = name.lower()
		if name in self.data: return self.data[name]
		return ''
	
	def lastTime(self,atype=''):
		if atype:
			last = self.get('last' + atype)
		else:
			last = self.get('lastTime')
		try: return int(last)
		except: return 0
		
	def addTriggers(self,triggerArray,channel,atype):
		if not type(triggerArray) == type([]): triggerArray = [triggerArray]
		name = "Triggers" + atype + ":" + channel
		triggers = self.get(name)
		new = False
		for trig in triggerArray:
			if not ','+trig+',' in ','+triggers+',':
				new = True
				if triggers:
					triggers = ','.join((triggers,trig))
				else:
					triggers = trig
		self.set(name,triggers)
		return new
	

	def addFTPURL(self,URL,channel):
		self.set("FTPURL:" + channel,URL)
		return True
	

	def addXDCCTrigger(self,trigger,channel,ctcpOrmsg,nick):
		name = "TriggersXDCC:" + channel
		triggers = self.get(name)
		if trigger == '1': triggers = ''
		if self.xdccTemplate:
			if triggers:
				triggers = ','.join((triggers,self.xdccTemplate + trigger))
			else:
				triggers = self.xdccTemplate + trigger
		else:
			if triggers:
				triggers = ','.join((triggers,ctcpOrmsg + " " + nick + " XDCC Send #" + trigger))
			else:
				triggers = ctcpOrmsg + " " + nick + " XDCC Send #" + trigger
		self.set(name,triggers)
		return True
	

	def hasXDCC(self):
		return 'xdcc' in str(self.data.keys())
	

	def nickAtNetwork(self):
		return self.nickAtNet
	
	def save(self):
		self.xml.saveDict(self.data)
		
	def load(self):
		self.data = self.xml.loadDict()
	
	def stripColors(self,text):
		return re.sub(r"\x03{1}\d{0,2}(,\d{0,2}){0,1}",'',text).replace('\x02','').replace('\x16','').replace('\x0f','').replace('\x1f','')
	
	def getAd(self,atype,channel,withtime=False):
		atime = ''
		if withtime:
			last = self.lastTime(atype=atype)
			atime = '[' + time.strftime('%b %d %H:%M',time.localtime(last)) + '] \n'
		adtext = self.get(atype + ':' + channel)
		if adtext: return atime + adtext
		return ''

	def getAllAds(self,channel):
		ad = ''
		for t in ('FSERVE','XDCC','FTP','TDCC','LISTSERVER'):
			ad += self.getAd(t,channel,withtime=True)
		return ad
			
	def getStrippedAd(self,atype,channel):
		return self.stripColors(self.get(atype + ':' + channel))
	
	def getTriggers(self,atype,channel):
		if atype == 'FTP':
			trig = self.get('FTPURL:' + channel)
		else:
			trig = self.get('Triggers' + atype + ':' + channel)
		if trig: return trig.split(',')
		return []
	
	def getAllTriggers(self,channel):
		trigs = []
		for t in ('FSERVE','XDCC','FTP','TDCC','LISTSERVER'):
			trigs.extend(self.getTriggers(t,channel))
		return trigs
		
		

class DTAdFilter:
	def __init__(self):
		self.data = {}
		self.exceptions = {}
		self.ads = {}
		self.set('name',"adfilter")
		self.types = ('FSERVE','FTP','XDCC','TDCC','LISTSERVER','REQUEST','NICK')
		self.set('filterFSERVEAds',1)
		self.set('filterFTPAds',0)
		self.set('filterXDCCAds',1)
		self.set('filterTDCCAds',1)
		self.set('filterLISTSERVERAds',1)
		self.set('hideFilteredAds',1)
		#DTCron.runEachHour(self,saveAds)
	
	def __call__(self,data,*args,**kwargs):
		method,data = data.split(':',1)
		return getattr(self, method)(data,*args,**kwargs)
	
	def init(self):
		if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "", ""):
			global SAVEPATH
			SAVEPATH = os.path.join(weechat.info_get('weechat_dir',''),'darktower','adfilter')
			if not os.path.exists(SAVEPATH): os.makedirs(SAVEPATH)
			self.saveFile = os.path.join(SAVEPATH,'adfilter.DT')
			self.exceptFile = os.path.join(SAVEPATH,'AFexceptions.DT')
		
			weechat.hook_command("adfilter", "Dark Tower AdFilter Commands",
				"[COMMANDS]",
				"[COMMANDS DETAIL]",
				"[COMPLETION]",
				"AdFilter", "command_cb:")
			
			weechat.hook_modifier("irc_in_PRIVMSG", "AdFilter","privmsg_event:")
			
		self.loadAds()
		self.loadExceptions()
		
	def command_cb(self,data,bufr,args):
		args = args.split()
		if args[0].lower() == 'show':
			target = None
			if len(args) > 1:
				target = args[1]
				nick, network = target.split('@')
				network,channel = network.split('#')
				ad = DTChannelAd(nick,network)
				ad.load()
				#print ad.__dict__
				weechat.prnt(weechat.current_buffer(),ad.stripColors(ad.getAllAds('#'+channel)))
		return weechat.WEECHAT_RC_OK
			
	
	def privmsg_event(self,data, modifier, server, string):
		parsed = weechat.info_get_hashtable("irc_message_parse", { "message": string })
		args = parsed['arguments'].split(None,1)[-1][1:]
		text = args.strip(chr(1))
		nick = parsed['nick'] #data.split()[0].split('!')[0][1:]
		target = parsed['channel']
				
		atype = self.isAdMessage(text,nick,'CHANNEL',target,server)
		if atype:
			if self.processAdMessage(atype,text,target,server,nick): return ''
		return string
			
	def set(self,name,value): #@ReservedAssignment
		self.dataChangeEvent(name,value)
		self.data[name] = value

	def get(self,name):
		if name in self.data: return self.data[name]
		return None

	def dataChangeEvent(self,name,value): pass

	def __del__(self):
		self.saveAds()
		self.saveExceptions()
	

	def addAd(self,atype,message,channel,network,nick):
		nickNet = nick + "@" + network
		ad  = self.getAdByNickNet(nickNet)
		if ad:
			ad.set(atype + ":" + channel,message)
			return ad
		
		ad = DTChannelAd(nick,network)
		ad.set('type',atype)
		ad.set('channels',channel)
		ad.set(atype + ":" + channel,message)
		ad.set('lastTime',time.time())
		self.ads[nickNet] = ad
		self.newAdEvent(ad)
		return ad
	

	def removeAd(self,nickAtNet,atype,channel):
		ad  = self.getAdByNickNet(nickAtNet)
		if not ad: return
		ad.set(atype + ":" + channel,"")
		#self.emit("AdRemoved")
	

	def removeEntireAd(self,adObject,supressSignal):
		nickNet = adObject.get('nickNet')
		del self.ads[nickNet]
		#if(!1) self.emit("AdRemoved");
	

	def removeOldAds(self,secondsOld):
		now = time.time()
		for ad in self.ads:
			age = ad.get('lastTime')
			if now - age > secondsOld:
				self.removeEntireAd(ad,1)
			
		#self.emit("AdRemoved");
	
	def saveAds(self): pass
	'''
		if not self.ads: return
		cid = config.open(self.saveFile,w);
		foreach(nickAtNet,keys(self.ads)):
			ad = self.ads['nickAtNet'];
			config.setsection cid nickAtNet;
			foreach(key,keys(ad.data)) config.write cid key ad.data['key'];
		
		config.close cid;
	'''
	

	def loadAds(self):
		for p in os.listdir(SAVEPATH):
			if p[-3:] == '.DT': continue
			nick,net = os.path.splitext(p)[0].split('@')
			ad = DTChannelAd(nick,net)
			ad.load()
			self.ads[ad.nickAtNet] = ad
		
	def addException(self,nick,chan,network):
		self.exceptions[chan + "@" + network + ":" + nick] = 1
		self.saveExceptions()
	

	def removeException(self,nick,chan,network):
		self.exceptions[chan + "@" + network + ":" + nick] = ''
		self.saveExceptions()
	
	def hasException(self,val):
		return val in self.exceptions
	
	def loadExceptions(self):
		self.exceptions = {}
		if not os.path.exists(self.exceptFile): return
		fi = open(self.exceptFile,'r')
		data = fi.read().splitlines()
		fi.close()
		for d in data: self.exceptions[d] = 1

	def saveExceptions(self):
		if not self.exceptions: return
		out = ''
		for key in self.exceptions:
			out += key + '\n'
		fi = open(self.exceptFile,'w')
		fi.write(out)
		fi.close()
		
	def appendFServeAd(self,atype,message,channel,network,nick):
		nickNet = nick + "@" + network
		ad = self.getAdByNickNet(nickNet)
		if ad:
			adtext = ad.get(atype + ":" + channel) + message;
			ad.set(atype + ":" + channel,adtext)
			ad.set('lastTime',time.time());
			return ad
		else:
			return self.addAd(atype,message,channel,network,nick)
		
	
	def getAdByNickNet(self,nickAtNet):
		if not nickAtNet: return
		if not nickAtNet in self.ads: return
		return self.ads[nickAtNet]

	def stripColors(self,text):
		#K = '\x03'
		#B = '\x02'
		#U = '\x31'
		#R = '\x22'
		#O = '\x15'
		return re.sub(r"\x03{1}\d{0,2}(,\d{0,2}){0,1}",'',text).replace('\x02','').replace('\x16','').replace('\x0f','').replace('\x1f','')
	
	def isAdMessage(self,msg,nick,msgSource,chanName,network):
		msg = msg.lower()
		
		if msgSource == 'CHANNEL' and self.hasException(chanName + "@" + network + ":" + nick): return False
		
		#LISTSERVER - before fserve because may have 'trigger' in it
		if 'list' in msg:
			msg = self.stripColors(msg)
			if re.search(r"^.*type:.*@.*list.*",msg): return "LISTSERVER"
			if "list trigger" in msg: return "LISTSERVER"
		
		#FSERVE
		if "rigger" in msg or "erv" in msg:
			msg = self.stripColors(msg)
			if ('ile' in msg and 'erver' in msg) or ('fserve up' in msg) or ('rigger' in msg and 'erv' in msg):
				if not 'rigger' in msg: return "FSERVE2"
				return "FSERVE"
			
		
		#TDCC
		if 'tdcc' in msg:
			msg = self.stripColors(msg)
			if re.search(r'.*active.*|.*online.*|.*t' + u'\xAE\xEE' + 'gg' + u'\xCB\xAE' + '.*|.*rigger.*',msg):
				if not 'rigger' in msg: return 'TDCC2'
				return "TDCC"
			
		
		#FTP
		if 'ftp' in msg[:30]:
			msg = self.stripColors(msg)
			if 'ftp active' in msg or 'ftp online' in msg: return 'FTP'
		
		#XDCC
		if self.checkXDCC(msg,nick,network):
			#check if this is just a status notice from the xdcc server
			if msgSource != "CHANNEL" and ('sending' in msg or 'queued' in msg or 'completed' in msg): return False
			if 'added' in msg: return False
			return "XDCC"
		
		return False
	

	def checkXDCC(self,msg,nick,network):
		msg = msg.lower()
		if 'xdcc' in msg:
			if 'server' in msg or '\x03' in msg: return "XDCC"
			msg = self.stripColors(msg)
			if re.search(r".*(/ctcp|/msg)\s.*\sxdcc\ssend.*",msg): return "XDCC"
		
		if 'xdcc' in msg or self.hasXDCC(nick + "@" + network):
			if re.search(".*\x03.*|.*\x0f.*|.*\x1f.*",msg): return "XDCC"
			msg = self.stripColors(msg);
			if re.search(r".*pack.*|.*slot.*|.*bandwidth.*|.*/ctcp.*|.*/msg.*|.*total.*|.*usage.*|.*offered.*|.*record.*|.*motd.*|.*!w*.*",msg): return "XDCC"
		
		if '#' in msg:
			msg = self.stripColors(msg)
			if re.search(r"^(\W\#|\#)\d.*\w*\.\w*.*",msg) or re.search(r"^(\W\#|\#)\d.*\w*.*\(.*gets\).*",msg): return "XDCC"
		return False
	

	def hasXDCC(self,nickAtNetwork):
		ad = self.getAdByNickNet(nickAtNetwork)
		if ad: return ad.hasXDCC()
	
	def processAdMessage(self,atype,message,channel,network,nick):
		self.ctcp = False
		if not channel:
			self.ctcp = 1
			channel = self.channel
			if not channel: channel = "!list"
		ad = None
		if atype == "FSERVE":
			if self.get('filterFSERVEAds'): ad = self.processFServeAd(self.addAd(atype,message,channel,network,nick),channel,atype)
			else: return False
		elif atype == "FSERVE2":
			if self.get('filterFSERVEAds'): ad = self.appendFServeAd("FSERVE",message,channel,network,nick)
			else: return False
		elif atype == "FTP":
			if self.get('filterFTPAds'): ad = self.processFTPAd(self.addAd(atype,message,channel,network,nick),channel)
			else: return False
		elif atype == "XDCC":
			if self.get('filterXDCCAds'): ad = self.processXDCCAd(message,channel,network,nick);
			else: return False	
		elif atype == "TDCC":
			if self.get('filterTDCCAds'): ad = self.processFServeAd(self.addAd(atype,message,channel,network,nick),channel,atype)
			else: return False
		elif atype == "TDCC2":
			if self.get('filterTDCCAds'): ad = self.appendFServeAd("TDCC",message,channel,network,nick)
			else: return False
		elif atype == "LISTSERVER":
			if self.get('filterLISTSERVERAds'): ad = self.processListServerAd(self.addAd(atype,message,channel,network,nick),channel)
			else: return False
		if ad: ad.save()
		if self.get('hideFilteredAds'): return True
		return False
	

	def processFServeAd(self,ad,channel,atype):
		ad.set('lastTime',time.time())
		ad.set('lastFServe',time.time())
		adtext = ad.get(atype + ":" + channel)
		parsedTrigsArray = self.parseTriggers(adtext,ad.get('nick'));
		new = ad.addTriggers(parsedTrigsArray,channel,atype)
		if new: self.newTriggersEvent(ad)
		return ad
	

	def parseTriggers(self,ad,nick):
		ad = ad.replace("trigger(s)","triggers")
		ad = ad.replace("triggers:","triggers[")
		ad = ad.replace("trigger:","triggers[")
		ad = ad.replace("//","/")
		if '\x03' in ad:
			triggers = self.parseColorTriggers(ad,nick)
			if not triggers: return self.parseMonoTriggers(ad,nick)
			return triggers
		else:
			return self.parseMonoTriggers(ad,nick)

	def parseColorTriggers(self,ad,nick):
		ad = ad.lower()
		parsedTrigsArray = []
		if '/dccserver' in ad and "| ctcp" in ad:
			for trig in re.split(r'\x03|&|\x0f|\x1f',ad):
				if '/dccserver' in trig:
					parsedTrigsArray.append( "/" + self.stripColors(trig.split("| ",1)[-1]).strip() )
			
		else:
			if '/ctcp' in ad:
				for trig in re.split(r'\x03|&|\x0f|\x1f',ad):
					if '/ctcp' in trig:
						parsedTrigsArray.append( "/" + self.stripColors(trig.split("/",1)[-1]).strip() )
			else:
				ad = self.stripColors(ad)
				triggers = self.tokenAfterMatch(ad,'{}()' + u'\xAB\xBB' + '|[]:',"rigger")
				if triggers:
					triggers = re.split(r"([^\w! ])+",triggers)
					ctcp = ''
					if self.tokenAfterMatch(ad,'{}()'+u'\xAB\xBB'+'|[]',"ctcp") == "on": ctcp = "/ctcp "+nick+" "
					for t in triggers:
						if t: parsedTrigsArray.append(ctcp + t.strip())
			
		
		if '/dccserver' in ad:
			tmp = []
			for t in parsedTrigsArray: tmp.append(t.replace("ctcp","dsctcp"))
			parsedTrigsArray = tmp
		
		final = []
		for t in parsedTrigsArray:
			if len(t) > 3: final.append(t)
		return final
	

	def parseMonoTriggers(self,ad,nick):
		ad = self.stripColors(ad.lower());
		split = '{}()'+u'\xAB\xBB'+'|[]:';
		if "| ctcp" in ad: split = '{}()'+u'\xAB\xBB'+'[]:'
		triggers = self.tokenAfterMatch(ad,split,"rigger").lower()
		parsedTrigsArray = []
		if ("/ctcp" in ad or "| ctcp" in ad) and "/dccserver" in ad:
			if 'ctcp' in triggers:
				prefix = "/ctcp"
			else:
				if "| dccserver" in triggers: prefix = "/mode"
				else: prefix = "/dccserver"
			
			if self.hasMultiplePrefixedTriggers(triggers,prefix):
				split = self.getPrefixedTriggerSeparator(triggers,prefix);
				triggers = triggers.split(split)
			
			start = "/"
			if prefix != "/ctcp": start = "| "
			for t in triggers:
				if t: parsedTrigsArray.append("/" + self.stripColors(t).strip().rsplit(start,1)[-1])
		else:
			triggers = re.split(r"([^\w! ])+",triggers)
			ctcp = ''
			if self.tokenAfterMatch(ad,'{}()'+u'\xAB\xBB'+'|[]',"ctcp") == "on": ctcp = "/ctcp " + nick + " "
			for t in triggers: parsedTrigsArray.append(ctcp + t.strip())
		
		if "/dccserver" in ad:
			tmp = []
			for t in parsedTrigsArray: tmp.append(t.replace("ctcp","dsctcp"))
			parsedTrigsArray = tmp
		
		final = []
		for t in parsedTrigsArray:
			if len(t) > 3: final.append(t)
		return final
	

	def hasMultiplePrefixedTriggers(self,triggers,prefix):
		if len(triggers) - len(triggers.replace(prefix,'')) > len(prefix): return True
	

	def getPrefixedTriggerSeparator(self,triggers,prefix):
		temp = triggers.split(prefix)
		if len(temp) > 1: temp = temp[1].strip().split(' ')
		index = len(temp)
		if not index: return "&"
		index -= 1
		if len(temp) > index: return temp[index]
		return "&"
	
	'''
	def processFTPAd(self,ad,1=channel):
		ad.set(lastTime,time.time());
		ad.set(lastFTP,time.time());
		text = str.replace(ad.get("FTP:"1),".","..");
		if(str.contains(text,K)):
			text =~ s/B//g;
			text =~ s/O/K/g;
			text =~ s/U//g;
			colorSplit = str.split(K,text);
			#echo colorSplit;
			ip = str.grep("*\.*\.*",colorSplit,w);
			if(length(ip) > 1) ip = ip[0];
			ip = str.stripcolors(Kip);
			ip = str.strip(ip);
			if(str.contains(ip,":")):
				ipport = ip;
				port = str.split(":",ipport)[1];
				ip = str.split(":",ipport)[0];
				if(!isNumeric(port)):
					ip = port;
					port = str.split(":",ipport)[2];
				
			
			lp = self.elementAfterMatch(colorSplit,"l/p");
			if(!lp) lp = self.elementAfterMatch(colorSplit,"l:p");
			if(!lp) lp = self.elementAfterMatch(colorSplit,":pass");
			if(!lp) lp = self.elementAfterMatch(colorSplit,"/pass");
			if(lp):
				lp = str.strip(str.stripcolors(Klp));
				user = str.token(0,"/:",lp);
				pass = str.token(1,"/:",lp);
			
			if(!user) pass =;
			if(!pass) user =;
			if(!user) user = str.strip(str.stripcolors(Kself.elementAfterMatch(colorSplit,"login")));
			if(!user) user = str.strip(str.stripcolors(Kself.elementAfterMatch(colorSplit,"user")));
			if(!pass) pass = str.strip(str.stripcolors(Kself.elementAfterMatch(colorSplit,"pass")));
			if(!port) port = str.strip(str.stripcolors(Kself.elementAfterMatch(colorSplit,"port")));
		else:
			ipport = self.tokenMatch(text,'{}()'+u'\xAB\xBB'+'|[] ',"*\.*\.*:*");
			port = str.split(":",ipport)[1];
			ip = str.split(":",ipport)[0];
			if(!isNumeric(port)):
				ip = port;
				port = str.split(":",ipport)[2];
			
			split = '{}()'+u'\xAB\xBB'+'|[]:';
			if(!ip) ip = self.tokenAfterMatch(text,split,"address");
			if(!ip) ip = self.tokenAfterMatchAt(text,split,"ip",0);
			ip = str.strip(ip);
			if(str.contains(ip,":")):
				ipport = ip;
				port = str.split(":",ipport)[1];
				ip = str.split(":",ipport)[0];
				if(!isNumeric(port)):
					ip = port;
					port = str.split(":",ipport)[2];
				
			
			lp = self.tokenAfterMatch(text,split,"l/p");
			if(!lp) lp = self.tokenAfterMatch(text,split,"l:p");
			if(!lp) lp = self.tokenAfterMatch(text,split,":pass");
			if(!lp) lp = self.tokenAfterMatch(text,split,"/pass");
			if(lp):
				lp = str.strip(lp);
				user = str.token(0,"/:",lp);
				pass = str.token(1,"/:",lp);
			
			test = str.split(" ",pass);
			if(length(test) > 1) pass = test[0];
			if(!user) pass =;
			if(!pass) user =;
			if(!user) user = str.strip(self.tokenAfterMatch(text,split,"login"));
			if(!user) user = str.strip(self.tokenAfterMatch(text,split,"user"));
			if(!pass) pass = str.strip(self.tokenAfterMatch(text,split,"pass"));
			if(!port) port = str.strip(self.tokenAfterMatch(text,split,"port"));
		
		ip = str.replace(ip,"","/");
		#echo ip;
		#echo user;
		#echo pass;
		#echo port;
		new = 0.addFTPURL("ftp://"user":"pass"@"ip":"port,1);
		if(new) self.newTriggersEvent(0);
	'''
	
	def processListServerAd(self,ad,channel):
		ad.set('lastTime',time.time())
		ad.set('lastListServer',time.time())
		trigger = "@" + ad.get('nick')
		new = ad.addTriggers(trigger,channel,"LISTSERVER")
		if new: self.newTriggersEvent(ad)
		return ad

	def processXDCCAd(self,msg,channel,network,nick):
		nickAtNetwork = nick + "@" + network
		ad = self.getAdByNickNet(nickAtNetwork);
		if not ad:
			ad = self.addAd("XDCC",msg,channel,network,nick)
		else:
			ad.set('lastTime',time.time())
			ad.set('lastXDCC',time.time())
			if time.time() - ad.xdccLast > 20:
				ad.set("XDCC:" + channel,msg)
			else:
				text = ad.get("XDCC:" + channel)
				ad.set("XDCC:" + channel,text + '\n' + msg)
			
		
		ad.xdccLast = time.time();
		if re.search(r".*(/ctcp|/msg)\s.*\sxdcc\ssend.*",msg):
			ad.xdccTemplate = "/" + msg.split("/",1)[-1].split("#",1)[0] + "#"
		
		trig = self.stripColors(msg)
		if re.search(r"^(\W\#|\#)\d.*",trig):
			trig = trig.split("#",1)[-1].split()[0]
			ctcp = "/ctcp";
			if '/msg' in ad.get("XDCC:"+ channel): ctcp = "/msg"
			ad.addXDCCTrigger(trig,channel,ctcp,nick)
			self.newTriggersEvent(ad)
		
		return ad
	
	'''
	def processSlotsMessage(self,nick,1=slotsMessage):
		if not self.get('handleCTCPSlots'): return False
		network = my.network;
		ad = self.getAdByNickNet(0"@"network);
		if(ad):
			keys = array("slotsMax","slotsCurrent","nextSend","queues","maxQueues","cps","filecount","bytesServed","mode","indexedtime.time()","servTime");
			ct=0;
			foreach(item,str.split(" ",1)):
				key = keys[ct];
				if(!key) break;
				slots['key'] = item; ct++;
			
			ad.slots = slots;
		
		return 1;
	'''
	def elementAfterMatch(self,thelist,find):
		ct=0
		for e in thelist:
			ct += 1
			if find in e.lower(): return thelist[ct]
		
	
	def token(self,index,sep,string):
		split = re.split('[' + re.escape(sep) + ']',string)
		if index < len(split): return split[index]
		return ''
		

	def tokenAfterMatch(self,string,split,match):
		check = "*"
		x=0
		while check:
			check = self.token(x,split,string)
			x+=1
			if match in check: return self.token(x,split,string)
		return ''
		
	def tokenAfterMatchAt(self,string,split,match,index):
		check = "*"
		x=0
		while check:
			check = self.token(x,split,string)
			x+=1
			if check.find(match) == 3: return self.token(x,split,string)
		return ''
		
	def tokenMatch(self,string,split,match):
		check = "*"
		x=0
		while check:
			check = self.token(x,split,string)
			if fnmatch.fnmatchcase(check.lower(),match): return str.token(x,split,string)
			x+=1
		return ''
		
	

	def newTriggersEvent(self,adObject): pass
		#self.emit(newTriggers,0);
	

	def newAdEvent(self,adObject): pass
		#self.emit(newAd,0);

AdFilter = DTAdFilter()
AdFilter.init()