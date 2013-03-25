
'''TODO:
	send timer
	log to weechat.log_print(message)?
'''


import os, sys, re, time, traceback, binascii, fnmatch, socket, textwrap

SCRIPT_NAME    = "DarkTowerFServe"
SCRIPT_AUTHOR  = "ruuk"
SCRIPT_VERSION = "0.0.1"
SCRIPT_LICENSE = "GPL2"
SCRIPT_DESC    = "FServe style file server"

####################################################################################
##
##  Classes
##
####################################################################################
class Saveable:
	#list or tuple of 3-item tuples (attribute_name,var_type,display_name,default,type_hint)
	saveAttrs = []
	parent = ''
	
	def getAttrType(self,attr):
		for a in self.saveAttrs:
			if attr == a[0]:
				return a[1]
		return None
			
	def getSaveAttrInfoByIndex(self,idx):
		if idx > -1 and idx < len(self.saveAttrs):
			return self.saveAttrs[idx]
		return None
			
	def setSaveAttr(self,attr,value):
		try:
			value = self._validateData(attr,value)
		except:
			return False
		
		self.setData(attr, self.getAttrType(attr), value)
		return True
		
	def validateData(self,attr,value):
		try:
			value = self._validateData(attr,value)
		except Exception, e:
			return e.message
		return True
		
	def extraValidateData(self,attr,atype,val): return val
	
	def _validateData(self,attr,value):
		atype = self.getAttrType(attr)
		if not atype: raise Exception('NO MATCHING ATTRIBUTE')
		
		if atype == 'string':
			pass
		elif atype == 'integer':
			try:
				value = int(value)
				if value < 0:
					raise Exception('NEGATIVE VALUE')
			except:
				raise Exception('BAD NUMBER')
		elif atype == 'boolean':
			if value.lower() == 'on':
				value = True
			elif value.lower() == 'off':
				value = False
			else:
				raise Exception('MUST BE ON OR OFF')
		elif atype == 'list':
			tmp = value.split(',')
			value = [] 
			for t in tmp:
				if t: value.append(t.strip())
			
		return self.extraValidateData(attr,atype,value)
	
	def getSaveAttr(self,ainfo,new=False):
		attr = ainfo[0]
		atype = self.getAttrType(attr)
		if not atype: return
		if attr == 'name': return self.name or ''
		if new: val = ainfo[3]
		else:
			val = self.getData(attr, atype)
		if atype == 'boolean':
			return val and 'On' or 'Off'
		elif atype == 'list':
			if not val: return ''
			return ','.join(val)
		else:
			return str(val)
		
	def getSaveAttrsAsDict(self,new=False):
		adict = {}
		for a in self.saveAttrs:
			adict[a[0]] = self.getSaveAttr(a,new)
		return adict
	
	def updateSaveAttrsFromDict(self,adict):
		for k,v in adict.items():
			if k == 'name':
				self.name = v
			self.setSaveAttr(k, v)
		self.dataUpdated(adict)
			
	def changeName(self,new): pass
	
	def getData(self,attr,atype):
		data = self.fserve._getData(self.parent, self.name, attr, atype)
		if atype == 'list':
			data = data.strip()
			return data and data.split(',') or []
		return data
	
	def setData(self,attr,atype,value):
		if atype == 'list':
			value = ','.join(value)
		self.fserve._setData(self.parent, self.name, attr, value)
		
	def dataUpdated(self,adict): pass
			
class Trigger(Saveable):
	saveAttrs = (	('name','string','Name','',''),
					('trigger','string','Trigger','',''),
					('path','string','Path','','dir'),
					('queue','string','Queue','','queue'),
					('channels','list','Channels','','channels'),
					('blacklist','list','File Blacklist','','string'),
					('whitelist','list','File Whitelist','','string'),
					('active','boolean','Active',False,'')
				)
	parent = 'triggers'
			
	def __init__(self,fserve,name):
		self.fserve = fserve
		self.name = name
	
	def active(self,change=None):
		if change == None:
			return bool(self.getData('active','boolean') and self.queue() and os.path.exists(self.path()) and self.queue().active())
		self.setData('active', 'boolean', change)
		
	def queue(self):
		return self.fserve.getQueue(self.getData('queue', 'string'))
	
	def sendpool(self):
		return self.queue().sendpool()
	
	def trigger(self):
		return self.getData('trigger', 'string')
	
	def path(self):
		return self.getData('path', 'string')
		
	def blacklist(self):
		return self.getData('blacklist', 'list')
		
	def whitelist(self):
		return self.getData('whitelist', 'list')
		
	def channels(self):
		return self.getData('channels', 'list')

	def extraValidateData(self, attr, atype, val):
		if attr == 'name':
			if val in self.fserve.triggers and not val == self.name:
				raise Exception('DUPLICATE TRIGGER NAME')
			else:
				return val
		elif attr == 'trigger':
			if val == self.trigger(): return val
			for t in self.fserve.triggers.values():
				if val == t.trigger(): raise Exception('DUPLICATE TRIGGER')
			else:
				return val
		elif attr == 'channels':
			for c in val:
				if not '@' in c or not c.startswith('#'):
					raise Exception('CHANNELS MUST BE COMMA SEPERATED WITH FORMAT: #channel@network')
				chanNet = c.split('@')
				if len(chanNet) < 2 or len(chanNet)>2:
					raise Exception('CHANNELS MUST BE COMMA SEPERATED WITH FORMAT: #channel@network')
			else:
				return val
		elif attr == 'path':
			if not val: return val
			if not os.path.isdir(val):
				if os.path.exists(val):
					raise Exception('NOT A DIRECTORY')
				else:
					raise Exception('DIRECTORY DOES NOT EXIST')
			return val
		elif attr == 'queue':
			if not val in self.fserve.queuePool.keys():
				raise Exception('QUEUE DOES NOT EXIST')
		return val
			
	def changeName(self,new):
		self.fserve.triggers[new] = self
		del self.fserve.triggers[self.name]
		self.name = new
		
	def isVisible(self,channel,network):
		return (channel + '@' + network) in self.channels()

class DirBrowser:
	def __init__(self,path,blacklist=None,whitelist=None):
		self.root = path
		self.currentRelativePath = ''
		self.blacklist = blacklist or []
		self.whitelist = whitelist or []
		
	def error(self,msg):
		#print '-- ERROR - ' + msg + ' - ERROR --'
		pass
		
	def currentPath(self,sub=''):
		if not sub: return os.path.join(self.root,self.currentRelativePath)
		return os.path.join(self.root,self.currentRelativePath,sub)
	
	def basePath(self):
		return os.path.basename(self.currentRelativePath)
	
	def changeDir(self,target):
		newPath = os.path.normpath(os.path.join('/',self.currentRelativePath,target))
		if newPath.startswith('/'): newPath = newPath[1:]
		if not os.path.exists(os.path.join(self.root,newPath)):
			self.error('ERROR CHANGING TO DIR: ' + target)
			return False
		self.currentRelativePath = newPath
		return True
		
	def listDir(self):
		entries = os.listdir(self.currentPath())
		dirs = []
		files = []
		pattern = '(?:.'+'|.'.join(self.blacklist or self.whitelist)+')$(?i)'
		for e in entries:
			if e.startswith('.'): continue
			full = os.path.join(self.currentPath(),e)
			if os.path.isdir(full):
				dirs.append(e)
			else:
				if self.blacklist:
					if not re.search(pattern,e): files.append(e)
				elif self.whitelist:
					if re.search(pattern,e): files.append(e)
				else:
					files.append(e)
		dirs.sort(key=str.lower)
		files.sort(key=str.lower)
		return (dirs,files)
	
	def isAtRoot(self):
		return not self.currentRelativePath.replace('/','').strip()
	
class FServeDirBrowser(DirBrowser):
	def __init__(self,trigger):
		DirBrowser.__init__(self,trigger.path(),trigger.blacklist(),trigger.whitelist())
		
class FserveSession:
	def __init__(self,user,interface=None,fserve=None,dirBrowser=None,trigger=None):
		self.user = user
		self.dirBrowser = dirBrowser
		self.interface = interface
		self.trigger = trigger
		self.lastCommand = ''
		self.fserve = fserve
		self.sessionIdleLimit = 30
		self.sessionIdleGrace = 10
		self.interface.startTimer()
		self.startTime = time.time()
		self.lastInput = self.startTime
		self.graceTimeStart = 0
		self.textColor = '\x0f'
		self.dataColor = '\x0304'
		self.deliColor = '\x0314'
		self.dirColor = '\x0306'
		self.trigColor = '\x0304'
		self.fileColor = '\x0303'
		
	##-- FUNCTIONS -------------------------------------------------------		
	def translateNumeric(self,numeric):
		numeric = numeric.lower()
		dirs,files = self.dirBrowser.listDir()
		ct = 1
		nm = int(numeric[:-1])
		if numeric.endswith('d'):
			if nm == 0: return '..'
			for d in dirs:
				if ct == nm: return d
				ct+=1
			else:
				return None
		else:
			for f in files:
				if ct == nm: return f
				ct+=1
			else:
				return None
			
	def colorize(self,text):
		return self.fserve.adManager.processTags(text, self.user, self.user.network, None)
	
	def showPrompt(self):
		self.interface.sendData(self.colorize('@[DEL][\x0f@[DIR]%s/\x0f@[DEL]]\x0f' % self.dirBrowser.basePath()))
		
	def showWelcome(self,main=False):
		if main:
			welcome = os.path.join(self.fserve.savePath,'welcome.DT')
		else:
			welcome = os.path.join(self.dirBrowser.currentPath(),'.welcome.DT')
		if not os.path.exists(welcome): return
		f = open(welcome,'r')
		msg = f.read()
		f.close()
		self.interface.sendData(self.colorize(msg + '\n '))
		if self.user.lastUnix:
			ago = time.time() - self.user.lastUnix
			ago = durationToShortText(ago)
			oldNick = ''
			if self.user.lastNickAtNetwork: oldNick = ' (as %s)' % self.user.lastNickAtNetwork
			self.interface.sendData(self.colorize('Welcome back. It has been @[DATA]%s\x0f since your last visit%s. This is visit number @[DATA]%s\x0f.' % (ago,oldNick,self.user.visits)))
		if self.user.downloadCount:
			size = simpleSize(self.user.downloaded)
			ago = durationToShortText(time.time() - self.user.firstUnix)
			self.interface.sendData(self.colorize('You have downloaded @[DATA]%s\x0f files (@[DATA]%s\x0f) in the last @[DATA]%s\x0f.\n ' % (self.user.downloadCount,size,ago)))
			
		
	##-- COMMANDS -------------------------------------------------------		
	def dir(self): #@ReservedAssignment
		self.showWelcome()
		dirs,files = self.dirBrowser.listDir()
		lines = []
		trigBase = '@[DEL][\x0f@[TRIGC]%s%s\x0f@[DEL]]\x0f @[DATA]%s\x0f @[DEL](\x0f@[TEXT]Trigger\x0f@[DEL])\x0f'
		dirBase = '@[DEL][\x0f@[DIR]%s%s\x0f@[DEL]]\x0f @[TEXT]%s\x0f/'
		fileBase = '@[DEL][\x0f@[FILE]%s%s\x0f@[DEL]]\x0f @[TEXT]%s\x0f - @[DATA]%s\x0f'
		if self.dirBrowser.isAtRoot():
			ct=1
			for t in self.fserve.triggers.values():
				if t != self.user.trigger():
					lines.append(trigBase % (ct,'t',t.trigger()))
					ct+=1
		ct=1
		for d in dirs:
			lines.append(dirBase % (ct,'d',d))
			ct+=1
		ct=1
		for f in files:
			size = 0
			try:
				size = simpleSize(os.path.getsize(self.dirBrowser.currentPath(f)))
				lines.append(fileBase % (ct,'f',f,size))
				ct+=1
			except OSError, e:
				LOG('Error Displaying Directory (%s): %s' % (f,e.strerror),'ERROR','lightred','lightred','notify_message')
		
		for l in lines: self.interface.sendData(self.colorize(l))
	
	def changeDir(self,target):
		if not self.dirBrowser.changeDir(target):
			self.changeTrigger(None,trigger=target)
		
	def changeTrigger(self,cmd,trigger=None):
		if trigger:
			for t in self.fserve.triggers.values():
				if t != self.user.trigger():
					if trigger == t.trigger():
						self.doChangeTrigger(t)
						break
			else:
				return False
			return True
		
		num = cmd[:-1]
		ct = 1
		for t in self.fserve.triggers.values():
			if t != self.user.trigger():
				if str(ct) == num:
					self.doChangeTrigger(t)
					break
				ct+=1
		else:
			return False
		return True
		
	def doChangeTrigger(self,t):
		self.user._lastTrigger = t.name
		self.dirBrowser = FServeDirBrowser(t)
		self.interface.sendData('Trigger changed to: ' + t.trigger())
		LOG('Changed trigger: %s' % t.trigger(),self.user.nickAtNetwork(),'lightgreen','lightblue','notify_message')
						
	def get(self,fname):
		path = os.path.join(self.dirBrowser.currentPath(),fname)
		if not os.path.exists(path):
			self.interface.sendData('File not found.')
			return
		item = QueueItem(self.user,path)
		err = self.user.queue().addItem(item)
		if err:
			if err == 'LIMIT':
				self.interface.sendData('Queue Limit (%s) Reached' % self.user.queue().max())
			elif err == 'USERLIMIT':
				extra = ''
				if self.user.queue().sendsCountAsQueues(): extra = ' Note: Sends count against this total.'
				self.interface.sendData(('User Queue Limit (%s) Reached.' % self.user.queue().maxPerUser()) + extra)
			elif err == 'EXISTS':
				self.interface.sendData('File Already Queued!')
			elif err == 'SENDING':
				self.interface.sendData('Already Sending File!')
		
	def queues(self):
		if not self.user.queue().items:
			self.interface.sendData('No Queues')
			return
		ct = 1
		for i in self.user.queue().items:
			self.interface.sendData(self.colorize('@[DEL][\x0f@[DATA]%s\x0f@[DEL]]\x0f @[TEXT]%s\x0f @[DEL]-\x0f @[TEXT]%s\x0f @[DEL](\x0f@[DATA]%s\x0f@[DEL])\x0f' % (ct,i.user.nickAtNetwork(),i.filename(),simpleSize(i.size))))
			ct += 1
			
	def sends(self):
		sendpool = self.user.queue().sendpool()
		sendDatas = self.fserve.xferCheck(direct=True)
		out = self.colorize('@[TEXT]%s\x0f @[DEL](\x0f@[DATA]%s/%s\x0f@[DEL]):\x0f ' % (sendpool.name,sendpool.sendCount(),sendpool.max()))
		if not sendpool.sends:
			self.interface.sendData(out + 'No Files Currently Sending')
		else:
			self.interface.sendData(out)
			self.showSends(sendpool,sendDatas) #Show current sendpool first
			
		for s in self.fserve.sendpools.values(): #Then show the other send pools
			if s != sendpool:
				out = self.colorize('@[TEXT]%s\x0f @[DEL](\x0f@[DATA]%s/%s\x0f@[DEL]):\x0f ' % (s.name,s.sendCount(),s.max()))
				if not s.sends:
					self.interface.sendData(out + 'No Files Currently Sending')
				else:
					self.interface.sendData(out)
					self.showSends(s, sendDatas)
		
	def showSends(self,sendpool,sendDatas):
		ct = 1
		for i in sendpool.sends:
			s = {}
			for s in sendDatas:
				if s['nick'] == i.user.nick and os.path.basename(s['fname']) == i.filename(): break
			else:
				s = {}
			pos = s.get('pos',0)
			size = s.get('size',1)
			#pct = calculatePercent(pos,size)
			bar = self.bar(pos, size)
			self.interface.sendData('\x0300,06|\x0f' + bar + '\x0300,06|\x0f ' + self.colorize( '@[DEL][\x0f@[DATA]%s\x0f@[DEL]]\x0f @[TEXT]%s\x0f@[DEL]:\x0f @[TEXT]%s\x0f @[DEL](\x0f@[DATA]%s\x0f@[DEL])\x0f @[DEL]@\x0f @[DATA]%s\x0f @[TEXT]KBps ETA@[DEL]:\x0f @[DATA]%s\x0f' % (ct,i.user.nickAtNetwork(),i.filename(),simpleSize(i.size),s.get('cps','?'),s.get('eta','?'))))
			ct += 1
			
	def bar(self,pos,size):
		barwidth = 10
		try:
			pos = int(pos)
			size = int(size)
		except:
			return barwidth*" "
		
		color1 = '\x0300,03'
		color2 = '\x0f\x0300,01'
		if size:
			width_per_size = (barwidth) / float(size)
			transf_chars = int(width_per_size * pos)
			non = 0 - (barwidth - transf_chars)
			prct = (size == 0) and "0%%" or '%s%%' % int((pos*100)/size)
			plen = len(prct)
			sides = barwidth - plen
			right = int(sides / 2)
			left = barwidth - (right + plen)
			filebar = " "*left + prct + " "*right
			if non: part2 = color2+filebar[non:]
			filebar = color1+filebar[0:transf_chars]+part2
			return filebar
		else:
			return barwidth*" "
		
	def clr_queues(self):
		queues = self.user.queue().clr_queues(self.user)
		if queues:
			LOG('Cleared queues from %s' % self.user.queue().name,self.user.nickAtNetwork(),'lightgreen','lightblue','notify_message')
		for q in queues:
			self.interface.sendData(self.colorize('@[TEXT]Clearing\x0f @[DATA]%s\x0f @[TEXT]from the queue.\x0f' % q.filename()))
		self.fserve.save()
		
	def clr_sends(self):
		sends = self.user.queue().sendpool().clr_sends(self.user)
		if sends:
			LOG('Canceled sends from %s' % self.user.queue().sendpool().name,self.user.nickAtNetwork(),'lightgreen','lightblue','notify_message')
		for q in sends:
			self.interface.sendData(self.colorize('@[TEXT]Canceling send of\x0f @[DATA]%s\x0f@[TEXT].\x0f' % q.filename()))
		self.fserve.save()
	
	def users(self):
		nicks = []
		for u in self.fserve.getUserList(): nicks.append(u.nickAtNetwork())
		self.interface.sendData('On FServe: ' + ', '.join(nicks))
		
	def quit(self): #@ReservedAssignment
		self.interface.sendData('Exiting')
		self.close()
		self.interface.quit()
		
	def close(self):
		self.user.updateLastOn()
		self.user.updateLastPath(self.dirBrowser.currentRelativePath)
		self.user.save()
		
	def resetTimes(self):
		self.lastInput = time.time()
		self.graceTimeStart = 0
		
	def timeCheck(self):
		now = time.time()
		if self.graceTimeStart:
			if now - self.graceTimeStart > self.sessionIdleGrace:
				LOG('Idle timeout',self.user.nickAtNetwork(),'lightgreen','lightred','notify_message')
				self.quit()
		else:
			if now - self.lastInput > self.sessionIdleLimit:
				self.interface.sendData('Session idle time limit (%ss) reached. Closing session in %s seconds...' % (self.sessionIdleLimit,self.sessionIdleGrace))
				LOG('Idle',self.user.nickAtNetwork(),'lightgreen','yellow','notify_message')
				self.graceTimeStart = now
		
	##-- EXTERNAL -------------------------------------------------------			
	def processCommand(self,cmd):
		if cmd == 'dir' or cmd == 'ls':
			self.dir()
		elif cmd == 'quit' or cmd == 'exit' or cmd == 'bye':
			self.quit()
		elif cmd == 'queues' or cmd == 'q':
			self.queues()
		elif cmd == 'sends' or cmd == 's':
			self.sends()
		elif cmd == 'clr_queues' or cmd == 'clr_q':
			self.clr_queues()
		elif cmd == 'clr_sends' or cmd == 'clr_s':
			self.clr_sends()
		elif cmd == 'users' or cmd == 'who':
			self.users()
		elif cmd == 'help' or cmd == '?':
			self.interface.sendData('cd [change your current directory (cd [directory|/|..])]')
			self.interface.sendData('#d [change your current directory to the numbered directory number # (ex 1d)')
			# clr_fqueues [deletes your failqueueslots this won't delete your queues (same as: clr_fqs|clrfqs)]
			# clr_queue [deletes one of your queues (clr_queue|del_q|clr_q <number>)]
			self.interface.sendData('clr_queues [deletes all your queues in current queue]')
			self.interface.sendData('clr_sends [cancels all your sends from current queue]')
			self.interface.sendData('dir [lists all files and directories in your current directory (same as: ls)]')
			# failq [lists your failqueues (failq|fq|failqueue <failqnumber>)]
			# find [searches fileserver. wildcards are supported (find <filename>)(same as: search)]
			self.interface.sendData('get [gets file from the file server (get <filename>)]')
			self.interface.sendData('#f [gets file number # from the file server (ex 1f)]')
			self.interface.sendData('help [displays this help menu]')
			# my_queues [lists your queueslots (same as: my_q|myq)]
			# pwd [shows your current directory]
			self.interface.sendData('queues [shows the list of waiting queues - shortcut: q)]')
			self.interface.sendData('sends [show currently sending files - shortcut: s]')
			self.interface.sendData('quit [closes this fserve session (same as: exit|bye)]')
			# time [shows when this session times out]
			self.interface.sendData('who [shows who else is on the file server (same as: users)]')
		elif re.match('\d+d$',cmd):
			fname = self.translateNumeric(cmd)
			if not fname:
				self.interface.sendData('Bad Directory Index: ' + cmd)
			else:
				self.changeDir(fname)
		elif re.match('\d+t$',cmd):
			if not self.changeTrigger(cmd): self.interface.sendData('Bad Trigger Index: ' + cmd)
		elif re.match('\d+f$',cmd):
			fname = self.translateNumeric(cmd)
			if not fname:
				self.interface.sendData('Bad File Index: ' + cmd)
			else:
				self.get(fname)
		elif cmd.startswith('cd '):
			self.changeDir(cmd.split(' ',1)[-1])
		elif cmd.startswith('get '):
			self.get(cmd.split(' ',1)[-1])
		else:
			self.resetTimes()
			return
		self.resetTimes()
		self.lastCommand = cmd
		self.showPrompt()
		
	def connected(self,ip):
		self.user.setIP(ip)
		self.user.addVisit()
		self.interface.sendData(str(externalLogo()))
		self.showWelcome(True)
		self.showPrompt()
		LOG('On fserve (%s)' % self.user.ip,self.user.nickAtNetwork(),'lightgreen','lightgreen','notify_message')

class User:
	ratings = ('~','*','&','!','@','%','+')
	def __init__(self,nick,network):
		self.nick = nick
		self.network = network
		self._queue = None
		self.ip = None
		self._lastTrigger = ''
		self.lastPath = ''
		self.lastNickAtNetwork = ''
		self.lastUnix = 0
		self.firstUnix = time.time()
		self.downloaded = 0
		self.downloadCount = 0
		self.visits = 0
		self.channels = []
		self.prefix = ''
		self.user = ''
		self.host = ''
		self.fserve = DARKTOWER
		self.loaded = False
		self.load()

	def load(self,skiptable=False):
		self.savePath = os.path.join(self.fserve.usersPath,self.nickAtNetwork())
		if not os.path.exists(self.savePath):
			if not skiptable: return self.checkIPTable()
		f = open(self.savePath,'r')
		data = f.read()
		f.close()
		dataDict = {}
		for l in data.splitlines():
			k,v = l.split('=',1)
			dataDict[k] = v
		if not self.ip: self.ip = dataDict.get('ip')
		self._lastTrigger = dataDict.get('trigger')
		self.lastUnix = float(dataDict.get('laston',0))
		self.lastPath = dataDict.get('lastpath')
		self.visits = int(dataDict.get('visits',0))
		self.firstUnix = float(dataDict.get('firston',0))
		self.downloaded = int(dataDict.get('downloaded',0))
		self.downloadCount = int(dataDict.get('downloadcount',0))
		self.loaded = True
		if not self.firstUnix: self.setFirstUnix()
		
	def checkIPTable(self):
		if not self.ip: return
		nickAtNetwork = self.fserve.ipTable.getNickAtNetwork(self.ip, self.nickAtNetwork())
		if nickAtNetwork == self.nickAtNetwork(): return
		LOG('Nick changed from %s' % nickAtNetwork,self.nickAtNetwork(),'lightgreen','lightblue','notify_message')
		self.lastNickAtNetwork = nickAtNetwork 
		savePath = os.path.join(self.fserve.usersPath,nickAtNetwork)
		if not os.path.exists(savePath): return
		os.rename(savePath, self.savePath)
		self.load(True)
		
	def save(self):
		out = ['ip=' + self.ip]
		out.append('trigger=' + self._lastTrigger)
		out.append('laston=' + str(self.lastUnix))
		out.append('firston=' + str(self.firstUnix))
		out.append('lastpath=' + self.lastPath)
		out.append('downloaded=' + str(self.downloaded))
		out.append('downloadcount=' + str(self.downloadCount))
		out.append('visits=' + str(self.visits))
		f = open(self.savePath,'w')
		f.write('\n'.join(out))
		f.close()
		
	def getInfo(self):
		if not self.trigger(): return #TODO: See if I need to make sure trigger is set
		chans = []
		prefix = ''
		user = ''
		host = ''
		lastRating = 99
		for c in self.trigger().channels():
			c,net = c.split('@')
			if not net == self.network: continue
			info = self.fserve.nickInfo(self.nick, c, self.network)
			if info:
				user = info.get('user','') or user
				host = info.get('host','') or host
				p = info.get('prefix','')
				chans.append(p + c)
				if not p in self.ratings: continue
				r = self.ratings.index(p)
				if r < lastRating: prefix = p
		self.channels = chans
		self.prefix = prefix
		self.user = user
		self.host = host
		
	def updateLastOn(self):
		self.lastUnix = time.time()
		self.save()
		
	def addVisit(self):
		self.visits += 1
		self.save()
		
	def addDownloaded(self,byte):
		self.downloaded += byte
		self.downloadCount += 1
		self.save()
		
	def updateLastPath(self,path):
		self.lastPath = path
		
	def setFirstUnix(self):
		self.firstUnix = time.time()
		
	def queue(self):
		if not self.trigger(): return None
		return self.trigger().queue()
	
	def sendpool(self):
		if not self.queue(): return None
		return self.queue().sendpool()
	
	def __eq__(self,other):
		if not hasattr(other,'nickAtNetwork'): return False
		return self.nickAtNetwork() == other.nickAtNetwork()
	
	def __str__(self):
		return self.toString()
	
	def nickAtNetwork(self):
		return self.nick + '@' + self.network
	
	def setIP(self,ip):
		if not ip: return
		self.ip = ip
		if not self.loaded:
			self.checkIPTable()
		else:
			self.fserve.ipTable.getNickAtNetwork(self.ip, self.nickAtNetwork())
		self.save() #Even if we've loaded, the IP may have changed so either way we save
		
	def sendCount(self,queue=None):
		if queue: return queue.sendpool().sendCount(self)
		if not self.queue(): return 0
		return self.queue().sendpool().sendCount(self)
	
	def toString(self):
		return self.nickAtNetwork()+':'+(self.ip or '')
	
	def trigger(self):
		return DARKTOWER.getTrigger(self._lastTrigger)
	
	@classmethod
	def fromString(cls,data):
		nickAtNetwork,ip = data.split(':')
		nick,network = nickAtNetwork.split('@')
		user = cls(nick,network)
		user.ip = ip or None
		return user
			
class QueueItem:
	def __init__(self,user=None,path='',queue=''):
		self.user = user
		self.path = path
		self._queue = queue
		if not queue and user: self._queue = user.queue().name
		self.size = 0
		if path: self.size = os.path.getsize(path)
		self.fails = 0
		self.unixQueued = time.time()
		self.unixSendStart = 0
		self.unixSendEnd = 0
		
	def queue(self):
		return DARKTOWER.getQueue(self._queue)
	
	def filename(self):
		return os.path.basename(self.path)
	
	def startSend(self):
		self.unixSendStart = time.time()
		
	def sendStop(self):
		self.unixSendStart = 0
		self.unixSendEnd = time.time()
		
	def isSending(self):
		return bool(self.unixSendStart)
	
	def toString(self):
		return dictToHex(self.__dict__)
	
	@classmethod
	def fromString(cls,data,queue=None):
		d = hexToDict(data)
		user = User.fromString(d['user'])
		qi = cls()
		qi.__dict__.update(d)
		user._queue = qi._queue
		qi.user = user
		return qi
	
class Queue(Saveable):
	saveAttrs = (	('name','string','Name','',''),
					('sendpool','string','Sendpool','','sendpool'),
					('max','integer','Max Slots',10,''),
					('maxPerUser','integer','Max Slots Per User',1,''),
					('active','boolean','Active',False,'')
				)
	parent = 'queues'
	def __init__(self,fserve,name):
		self.name = name
		self.fserve = fserve
		self.items = []
		
	def __str__(self):
		return self.name
	
	def active(self,change=None):
		if change == None:
			return bool(self.getData('active', 'boolean') and self.sendpool())
		self.setData('active', 'boolean', change)
		
	def sendpool(self):
		return self.fserve.getSendpool(self.getData('sendpool', 'string'))
	
	def max(self): #@ReservedAssignment
		return self.getData('max', 'integer')
	
	def maxPerUser(self):
		return self.getData('maxPerUser', 'integer')
	
	def extraValidateData(self, attr, atype, val):
		if attr == 'name':
			if val in self.fserve.queuePool and not val == self.name:
				raise Exception('DUPLICATE QUEUE NAME')
		elif attr == 'sendpool':
			if not val in self.fserve.sendpools.keys():
				raise Exception('SENDPOOL DOES NOT EXIST')
		return val
			
	def changeName(self,new):
		try:
			#point triggers to new name
			for t in self.fserve.triggers.values():
				if t.queue().name == self.name:
					t.setData('queue','string',new)
			#point queues to new name
			for qp in self.fserve.queuePool.values():
				for q in qp.items:
					if q._queue == self.name:
						q._queue = new
			#point queues in sendpools to new name
			for sp in self.fserve.sendpools.values():
				for q in sp.sends:
					if q._queue == self.name:
						q._queue = new
		except:
			traceback.print_exc()
		self.fserve.queuePool[new] = self
		del self.fserve.queuePool[self.name]
		self.name = new
	
	def sendsCountAsQueues(self):
		return self.fserve.sendsCountAsQueues()
	
	def addItem(self,queueitem,force=False):
		if not force:
			if len(self.items) >= self.max(): return 'LIMIT'
			if self.userItemCount(queueitem.user) >= self.maxPerUser(): return 'USERLIMIT'
		if self.fileQueued(queueitem): return 'EXISTS'
		if self.fileSending(queueitem): return 'SENDING'
		self.items.append(queueitem)
		self.fserve.checkForSends()
		slot = self.slotNumber(queueitem)
		if slot:
			self.fserve.sayFserveSession(queueitem.user,'@[DATA]%s\x0f @[TEXT]added to\x0f @[DATA]%s\x0f @[TEXT]in slot\x0f @[DATA]%s\x0f' % (queueitem.filename(),self.name,slot))
			LOG('Queued %s in slot %s of %s' % (queueitem.filename(),slot,self.name),queueitem.user.nickAtNetwork(),'lightgreen','lightblue','notify_message')
		self.fserve.save()
		return None
	
	def pushItem(self,queueitem):
		self.items.insert(0, queueitem)
		
	def removeItem(self,idx=None,item=None):
		if item: idx = self.items.index(item)
		if idx == None: raise Exception('Queue.removeItem(): Bad Queue Index')
		if not( self.count() > idx and self.count() > 0): return False
		self.items.pop(idx)
		self.fserve.save()
		return True
		
	def moveItem(self,item, targetitem):
		if not item in self.items or not targetitem in self.items: return None
		pos = self.items.index(targetitem)
		self.items.pop(self.items.index(item))
		self.items.insert(pos,item)
		self.fserve.save()
		return item
	
	def userItemCount(self,user):
		ct=0
		for i in self.items:
			if i.user == user: ct+=1
		if self.sendsCountAsQueues():
			ct += self.sendpool().sendCount(user)
		return ct
	
	def clr_queues(self,user):
		new = []
		cleared = []
		for q in self.items:
			if not user == q.user:
				new.append(q)
			else:
				cleared.append(q)
		self.items = new
		return cleared
		
	def fileQueued(self,queueitem):
		for q in self.items:
			if queueitem.user == q.user and queueitem.path == q.path: return True 
		return False
	
	def fileSending(self,queueitem):
		return self.fserve.fileSending(queueitem)
	
	def count(self):
		return len(self.items)
	
	def slotNumber(self,item):
		if item in self.items: return self.items.index(item) + 1
		return 0
	
	def next(self): #@ReservedAssignment
		ct = 0
		for q in self.items:
			if q.user.sendCount(self) < self.sendpool().maxPerUser():
				break
			ct += 1
		else:
			return None
		return self.items.pop(ct)
	
	def setItemsFromString(self,string):
		items = string.split('\n')
		if not items: return
		for i in items:
			if not i: continue
			q = QueueItem.fromString(i,self.name)
			if not q: continue
			self.items.append(q)

	def toString(self):
		items = []
		for i in self.items:
			items.append(i.toString())
		return self.name + '\n' + '\n'.join(items)
	
	@classmethod
	def fromString(cls,data,fserve):
		if not data: return None
		name,rest = data.split('\n',1)
		queue = cls(fserve,name)
		queue.setItemsFromString(rest)
		return queue			

class Sendpool(Saveable):
	saveAttrs = (	('name','string','Name','',''),
					('max','integer','Max Sends',1,''),
					('maxPerUser','integer','Max Sends Per User',1,''),
					('maxSpeed','integer','Max Speed (KBps)',0,'')
				)
	parent = 'sendpools'
	def __init__(self,fserve,name):
		self.name = name
		self.fserve = fserve
		self.sends = []
		
	def __str__(self):
		return self.name
	
	def max(self): #@ReservedAssignment
		return self.getData('max', 'integer')
	
	def maxPerUser(self):
		return self.getData('maxPerUser', 'integer')
	
	def maxSpeed(self): #@ReservedAssignment
		return self.getData('maxSpeed', 'integer')
		
	def extraValidateData(self, attr, atype, val):
		if attr == 'name':
			if val in self.fserve.sendpools and not val == self.name:
				raise Exception('DUPLICATE SENDPOOL NAME')
			else:
				return val
		return val
		
	def changeName(self,new):
		try:
			for q in self.fserve.queuePool.values():
				if q.sendpool().name == self.name:
					q.setData('sendpool','string',new)
		except:
			traceback.print_exc()
		self.fserve.sendpools[new] = self
		del self.fserve.sendpools[self.name]
		self.name = new
			
	def checkForSends(self):
		last = -1
		while self.sendCount() < self.max() and last != self.sendCount():
			last = self.sendCount()
			queue = self.fserve.getNextQueue(self)
			if not queue: return
			self.send(queue)
			
	def fileSending(self,queueitem):
		for q in self.sends:
			if queueitem.user == q.user and queueitem.path == q.path: return True
		return False
	
	def clr_sends(self,user):
		sends = []
		for s in self.sends:
			if s.user == user:
				sends.append(s)
				self.fserve.stopSend(s)
		return sends
				
	def send(self,q):
		self.sends.append(q)
		self.fserve.sayFserveSession(q.user,'Sending File: ' + os.path.basename(q.path))
		if not self.fserve.doSend(q.user.network, q.user.nick, q.path, speed=self.maxSpeed()):
			self.sends.pop()
		else:
			q.unixSendStart = time.time()
			LOG('Sending %s' % q.filename(),q.user.nickAtNetwork(),'lightgreen','lightmagenta','notify_message')
		self.fserve.save()
				
	def removeSend(self,q,status=''):
		reason = (status or 'Unknown').title()
		ret = False
		if q in self.sends:
			self.sends.pop(self.sends.index(q))
			if status == 'done': q.user.addDownloaded(q.size)
			LOG('Send stopped (%s): %s' % (reason,q.filename()),q.user.nickAtNetwork(),'lightgreen','lightmagenta','notify_message')
			ret =  True
			q.unixSendEnd = time.time()
		self.checkForSends()
		return ret
				
	def sendFinished(self,nick=None,network=None,path=None,ip=None,status=None):
		filename = os.path.basename(path)
#		secondCheck = False
		for q in self.sends:
			debug('-%s:%s:%s' % (q.user.nick,os.path.basename(q.path),q.user.ip))
			if q.user.ip:
				if q.user.ip == ip:
					fn = os.path.basename(q.path)
					if filenamesMatch(filename,fn):
						return self.removeSend(q,status)
#			else: #If for some reason the users IP is not set (though it always should be), do a check against nick and filename
#				secondCheck = True
#		if secondCheck:

		#If send never connects, IP will be local IP, so we have to check here if the IP fails
		#TODO: make a check above for local IP and only check here if remote IP is not set - to avoid accidentally matching the wrong send
		debug('frog')
		for q in self.sends:
			fn = os.path.basename(q.path)
			if q.user.nick == nick and q.user.network == network and filenamesMatch(filename,fn):
				debug('monkey')
				return self.removeSend(q,status)
		return False
	
	def sendCount(self,user=None):
		if not user: return len(self.sends)
		ct = 0
		for q in self.sends:
			if q.user == user: ct += 1
		return ct
	
	def setSendsFromString(self,string):
		if not string: return
		for line in string.splitlines():
			if not line: continue
			q = QueueItem.fromString(line)
			if not q: continue
			self.sends.append(q)
			
	def toString(self):
		sends = []
		for s in self.sends:
			sends.append(s.toString())
		return self.name + '\n' + '\n'.join(sends)
	
	@classmethod
	def fromString(cls,data,fserve):
		if not data: return None
		name , rest = data.split('\n',1)
		sendpool = cls(fserve,name)
		sendpool.setSendsFromString(rest)
		
		return sendpool
	
class BaseFserveSessionInterface():
	def __init__(self,fserve=None):
		self.fserve = fserve
			
	def sendData(self,data): pass
	
	def quit(self): pass #@ReservedAssignment
		
class WeeChatFserveSessionInterface(BaseFserveSessionInterface):
	def __init__(self,ID,fserve,user,trigger):
		self.id = ID
		fserveSession = FserveSession(user,interface=self,fserve=fserve,dirBrowser=FServeDirBrowser(trigger),trigger=trigger)
		fserveSession.fserve = fserve
		self.fserveSession = fserveSession
		BaseFserveSessionInterface.__init__(self, fserve=fserve)
		self.buffer = None
		self.messageHook = None
		self.timer = None
		
	def init(self):
		self.messageHook = weechat.hook_print(self.getBuffer(), "", "", 1, "DARKTOWER", "message_cb:" + self.id)
			
	def getBuffer(self):
		if not self.buffer:
			user = self.fserveSession.user
			self.buffer = weechat.buffer_search("xfer", 'irc_dcc.%s.%s' % (user.network,user.nick))
		return self.buffer
	
	def messageCallback(self,bufr, date, tags, displayed, highlight, prefix, message):
		if prefix == self.fserveSession.user.nick:
			self.fserveSession.processCommand(message)
		elif not prefix and 'Connected' in message and self.fserveSession.user.nick in message and 'xfer' in message:
			m = re.search('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',message)
			ip = None
			if m: ip = m.group(0)
			self.fserveSession.connected(ip)
			if not self.buffer:
				weechat.unhook(self.messageHook)
				self.messageHook = weechat.hook_print(self.getBuffer(), "", "", 1, "DARKTOWER", "message_cb:"+self.id)
		elif not prefix and 'chat closed' in message and self.fserveSession.user.nick in message and 'xfer:' in message:
			self.fserveSession.close()
			self.quit()
				
		return weechat.WEECHAT_RC_OK
	
	def sendData(self,message):
		buf = self.getBuffer()
		if not buf: return
		for m in message.splitlines():
			weechat.command(buf, m)
			
	def startTimer(self):
		self.timer = weechat.hook_timer(2 * 1000, 0, 0, "DARKTOWER","fserve_session_timer_cb:"+self.id)
	
	def stopTimer(self):
		if self.timer: weechat.unhook(self.timer)
		
	def timerCallback(self):
		self.fserveSession.timeCheck()
		
	def quit(self): #@ReservedAssignment
		if self.messageHook: weechat.unhook(self.messageHook)
		self.stopTimer()
		buf = self.getBuffer()
		if buf: weechat.command(buf,'/close')
		LOG('Off fserve',self.fserveSession.user.nickAtNetwork(),'lightgreen','lightred','notify_message')
		DARKTOWER.fserveQuit(self)

class IPTable:
	def __init__(self,fserve):
		self.fserve = fserve
		self.filePath = os.path.join(self.fserve.savePath,'iptable.DT')
		self.table = {}
		self.load()
		
	def load(self):
		if not os.path.exists(self.filePath): return
		f = open(self.filePath,'r')
		data = f.read()
		f.close()
		for l in data.splitlines():
			k,v = l.split('=',1)
			nickAtNetwork,unix = v.split('::')
			self.table[k] = (nickAtNetwork,int(unix))
		return self
			
	def save(self):
		items = self.table.items()
		items.sort(key=lambda x: x[1][1])
		items = items[:256]
		out = []
		for i in items:
			out.append(i[0] + '=' + i[1][0] + '::' + str(i[1][1]))
		f = open(self.filePath,'w')
		f.write('\n'.join(out))
		f.close()
		
	def getNickAtNetwork(self,ip,nickAtNetwork):
		if not ip: return nickAtNetwork
		saved = self.table.get(ip)
		self.table[ip] = (nickAtNetwork,int(time.time()))
		self.save()
		if saved: return saved[0]
		return nickAtNetwork
	
class ColorIRCToWeechat():
	ircRE = re.compile('\x03(\d{,2}(?:,\d{,2})?)')
	weechatColors = {	0:'white',
						1:'black',
						2:'blue',
						3:'green',
						4:'lightred',
						5:'red',
						6:'magenta',
						7:'brown',
						8:'yellow',
						9:'lightgreen',
						10:'cyan',
						11:'lightcyan',
						12:'lightblue',
						13:'lightmagenta',
						14:'gray',
						15:'white'
					}
	
	def __call__(self,text):
		return self.ircRE.sub(self.processIRCTag,text).\
				replace('\x0f',weechat.color('reset')).\
				replace('\x1f',weechat.color('underline')).\
				replace('\x02',weechat.color('bold')).\
				replace('\x16',weechat.color('reverse'))
		
	def transColor(self,c):
		if not c: return ''
		return self.weechatColors.get(int(c),'')
		
	def processIRCTag(self,m):
		try:
			f_b = m.group(1)
			f = f_b
			b = ''
			if ',' in f_b:
				f,b = f_b.split(',')
			color = self.transColor(f) + ',' + self.transColor(b)
			return weechat.color(color)
		except:
			traceback.print_exc()
			return m.group(0)
	

class Ad(Saveable):
	saveAttrs = (	('name','string','Name','',''),
					('active','boolean','Active',False,''),
					('interval','integer','Interval (Minutes)',60,''),
					('channels','list','Channels','','channels'),
					('silentChannels','list','Silent Channels','','channels'),
					('respondList','boolean','Respond to !list',False,''),
					('ad','string','Ad','','irctext')
				)
	parent = 'ads'
	
	def __init__(self,admanager,name):
		self.name = name
		self.manager = admanager
		self.fserve = admanager.fserve
		self.timerID = None
		
	def active(self,change=None):
		if change == None: return self.getData('active', 'boolean')
		if not change:
			self.fserve.stopAdTimer(self)
		else:
			self.fserve.startAdTimer(self)
		self.setData('active', 'boolean', change)
	
	def interval(self):
		return self.getData('interval', 'integer')
	
	def channels(self):
		return self.getData('channels', 'list')
	
	def silentChannels(self):
		return self.getData('silentChannels', 'list')
	
	def respondList(self,nick,channel,network):
		respond = self.getData('respondList', 'boolean')
		if not respond: return False
		if not channel + '@' + network in self.channels(): return False
		return True
	
	def dataUpdated(self,adict):
		self.checkInterval(adict)
		self.checkActive()
		
	def checkInterval(self,adict):
		if adict.get('interval') != self.interval():
			self.fserve.stopAdTimer(self)
			self.fserve.startAdTimer(self)
	
	def checkActive(self):
		if self.active() and not self.timerID:
			self.fserve.startAdTimer(self)
	
	def ad(self):
		return self.getData('ad', 'string')
	
class AdManager(Saveable):
	saveAttrs = (	('triggerFormat','string','Trigger Format','@[DEL][@[C] @[DATA]@[C:B]@[TRIG]@[C] @[DEL]:@[C] @[TEXT]S(@[C]@[DATA]@[S:COUNT]/@[S:MAX]@[C]@[TEXT])@[C] @[TEXT]Q(@[C]@[DATA]@[Q:COUNT]/@[Q:MAX]@[C]@[TEXT])@[C] @[DEL]]@[C]',''),
					('triggerSep','string','Trigger Separator','@[DEL]-@[C]','')
				)
	parent = 'admanager'
	tagRE = re.compile('@\[([\w:,]+?)\]')
	defRE = re.compile('@\[\{(.+?)\}\]')
	
	adTail = ' @[DEL]-@[C] @[TEXT]Dark Tower 4 WeeChat'
	
	def __init__(self,fserve):
		self.fserve = fserve
		self.ads = []
		self.processTagsContext = (None,None,None)
		self.defTable = {}
		self.name = 'admanager'
		self.weechatColorConvert = ColorIRCToWeechat()
	
	def adNames(self):
		names = []
		for a in self.ads: names.append(a.name)
		return names
	
	def removeAd(self,ad):
		ad = self.getAd(ad.name)
		self.fserve.startAdTimer(ad)
		self.ads.pop(self.ads.index(ad))
		
			
	def startAds(self):
		for a in self.ads:
			self.fserve.startAdTimer(a)
		
	def stopAds(self):
		for a in self.ads:
			self.fserve.stopAdTimer(a)
				
	def timerCallback(self,name):
		ad = self.getAd(name)
		if not ad: return
		if not ad.active():
			self.fserve.startAdTimer(ad)
			return
		for chanNet in ad.channels():
			if not chanNet in ad.silentChannels():
				channel,network = chanNet.split('@')
				self.fserve.doMessage(network, channel, self.processTags(ad.ad()+self.adTail, None, network, channel))
	
	def triggerFormat(self):
		#return '@[DEL][@[C] @[DATA]@[TRIG]@[C] @[DEL]:@[C] @[TEXT]S(@[C]@[DATA]@[S:COUNT]/@[S:MAX]@[C]@[TEXT])@[C] @[TEXT]Q(@[C]@[DATA]@[Q:COUNT]/@[Q:MAX]@[C]@[TEXT])@[C] @[DEL]]@[C]'
		return self.getData('triggerFormat', 'string')
	
	def triggerSep(self):
		#return '@[DEL]&\x0f'
		return self.getData('triggerSep', 'string')
	
	def doList(self,nick,channel,network):
		for ad in self.ads:
			if ad.active() and ad.respondList(nick,channel,network):
				self.fserve.doNotice(network, nick, self.processTags(ad.ad()+self.adTail, None, network, channel))
		
	def processTags4Weechat(self,text,context=None,network=None,channel=None):
		text = self.processTags(text, context, network, channel)
		return self.weechatColorConvert(text)
		
	def processTags(self,text,context=None,network=None,channel=None,init=True):
		if init: self.defTable = {}
		old = self.processTagsContext
		self.processTagsContext = (context,network,channel)
		text = self.defRE.sub(self.processDef,text)
		text = self.tagRE.sub(self.processTag,text)
		self.processTagsContext = old
		return text
	
	def processDef(self,m):
		try:
			name,data = m.group(1).split('=')
			self.defTable[name] = data
		except:
			return m.group(0)
	
	def processTag(self,m):
		try:
			tag = m.group(1)
			data = ''
			if ':' in tag:
				tag, data = tag.split(':',1)
			if tag in self.tagTable:
				return self.tagTable[tag](self,data)
			elif tag in self.defTable:
				return self.processTags(self.defTable[tag], *self.processTagsContext)
		except:
			return m.group(0)
	
	def parseDefArgs(self,args_string):
		args = args_string.split(',')
		ret = []
		for a in args:
			ret.append(self.defTable.get(a,''))
		return ret
			
	def tagTRIGGERS(self,data):
		context,network,channel = self.processTagsContext #@UnusedVariable
		triggers = []
		sep = form = None
		if data:
			sep,form = self.parseDefArgs(data)
		if not sep: sep = self.triggerSep()
		if not form: form = self.triggerFormat()
			
		for t in self.fserve.triggers.values():
			if t.active() and t.isVisible(channel,network):
				triggers.append(self.processTags(form, t, network, channel,init=False))
		return self.processTags(sep,t,network,channel,init=False).join(triggers)
	
	def tagTRIG(self,data):
		return '/ctcp %s %s' % (self.fserve.getClientNick(self.processTagsContext[1]),self.processTagsContext[0].trigger())
	
	def tagS(self,data):
		if data == 'MAX':
			return str(self.processTagsContext[0].sendpool().max())
		elif data == 'COUNT':
			return str(self.processTagsContext[0].sendpool().sendCount())
		return data
		
	def tagQ(self,data):
		if data == 'MAX':
			return str(self.processTagsContext[0].queue().max())
		elif data == 'COUNT':
			return str(self.processTagsContext[0].queue().count())
		return data
		
	def tagINDEX(self,data):
		if data == 'COUNT':
			return str(self.fserve.indexCount())
		elif data == 'SIZE':
			return simpleSize(self.fserve.indexSize())
	
	def tagDATA(self,data):
		return '\x0304'
	
	def tagTEXT(self,data):
		return '\x0f'
	
	def tagDEL(self,data):
		return '\x0314'
	
	def tagDIR(self,data):
		return '\x0306'
	
	def tagFILE(self,data):
		return '\x0303'
	
	def tagTRIGC(self,data):
		return '\x0304'
	
	def tagC(self,data):
		if data:
			if data == 'U':
				return '\x1f'
			elif data == 'B':
				return '\x02'
			elif data == 'R':
				return '\x16'
			else:
				return '\x03' + data
		else:
			return '\x0f'
	
	def tagUSER(self,data):
		if data == 'VISITS':
			return str(self.processTagsContext.visits)
		elif data == 'DOWNSIZE':
			return simpleSize(self.processTagsContext.downloaded)
		elif data == 'DOWNCOUNT':
			return str(self.processTagsContext.downloadCount)
		
	def getAd(self,name):
		for a in self.ads:
			if a.name == name: return a
			
	tagTable = 	{	'TRIGGERS':tagTRIGGERS,
					'TRIG':tagTRIG,
					'S':tagS,
					'Q':tagQ,
					'INDEX':tagINDEX,
					'DATA':tagDATA,
					'TEXT':tagTEXT,
					'DEL':tagDEL,
					'DIR':tagDIR,
					'FILE':tagFILE,
					'TRIGC':tagTRIGC,
					'C':tagC,
					'USER':tagUSER
				}
			
class FServe(Saveable):
	saveAttrs = (	('sendsCountAsQueues','boolean','Sends Count As Queues',True,''),
					('allowedChannelPrefixes','string','Allowed Channel Prefixes','#',''),
					('defaultQueue','string','Default Queue','','queue')
				)
	parent = 'general'
	
	def __init__(self):
		self.name = 'general'
		self.fserve = self
		self.currentID = -1
		self.fserveSessions = {}
		self.ipTable = None
		self.sendpools = {}
		self.triggers = {}
		self.queuePool = {}
		self.textColor = '\x0f'
		self.dataColor = '\x0304'
		self.deliColor = '\x0314'
		self.dirColor = '\x0306'
		self.fileColor = '\x0303'
		self.adManager = AdManager(self)
	
	def sendsCountAsQueues(self):
		return self.getData('sendsCountAsQueues', 'boolean')
	
	def allowedChannelPrefixes(self):
		return self.getData('allowedChannelPrefixes', 'string')
	
	def defaultQueue(self):
		queue = self.getData('defaultQueue', 'string')
		if not queue: queue = 'Main'
		if queue in self.fserve.queuePool: return queue
		if self.fserve.queuePool:
			return self.fserve.queuePool.values()[0].name
	
	def init(self):
		self.ipTable = IPTable(self)
		self.adManager.startAds()
		
	def sayFserveSession(self,user,message):
		for s in self.fserveSessions.values():
			if user == s.fserveSession.user:
				s.sendData(s.fserveSession.colorize(message))
				
	def getQueue(self,name):
		if name in self.queuePool: return self.queuePool[name]
		
	def getSendpool(self,name):
		if name in self.sendpools: return self.sendpools[name]
		
	def getTrigger(self,name):
		if name in self.triggers: return self.triggers[name]
		
	def getAd(self,name):
		return self.adManager.getAd(name)

	def nextID(self):
		self.currentID = str(int(self.currentID) + 1)
		return self.currentID
	
	def addSession(self,user,trigger):
		ID  = self.nextID()
		self.fserveSessions[ID] = WeeChatFserveSessionInterface(ID,self,user,trigger)
		return self.fserveSessions[ID]
		
	def fserveQuit(self,sessioninterface):
		if sessioninterface.id in self.fserveSessions: del self.fserveSessions[sessioninterface.id]
		
	def getUserList(self):
		ulist = []
		for s in self.fserveSessions.values():
			ulist.append(s.fserveSession.user)
		return ulist
	
	def assignQueue(self,user):
		user._queue = user.queue()
		
	def getNextQueue(self,sendpool):
		for q in self.queuePool.values():
			if q.sendpool().name == sendpool.name:
				return q.next()
		return None
		
	def fileSending(self,queueitem):
		for s in self.sendpools.values():
			if s.fileSending(queueitem): return True
		return False
	
	def sendCount(self):
		ct = 0
		for s in self.sendpools.values():
			ct += s.sendCount()
		return ct
	
	def checkForSends(self):
		for s in self.sendpools.values(): s.checkForSends()
		
	def sendLimit(self):
		ct = 0
		for s in self.sendpools.values():
			ct += s.max()
		return ct
	
	def colorize(self,text):
		return text.replace('@[TEXT]',self.textColor).\
					replace('@[DATA]',self.dataColor).\
					replace('@[DEL]',self.deliColor).\
					replace('@[DIR]',self.dirColor).\
					replace('@[FILE]',self.fileColor)
					
	def checkTrigger(self,network,nick,text):
		text = text.lower()
		for t in self.triggers.values():
			if t.active() and t.trigger().lower() == text:
				for c in t.channels():
					chan, net = c.split('@')
					if self.nickInChannel(nick, chan, net): break
				else:
					LOG('Typed trigger: %s - NOT IN FSERVE CHANNEL' % t.trigger(),nick + '@' + network,'lightgreen','yellow','notify_message')
					return False
				user = User(nick,network)
				user.getInfo()
				if self.userIsOnFserve(user):
					LOG('Typed trigger: %s - ALREADY ON FSERVE' % t.trigger(),user.nickAtNetwork(),'lightgreen','yellow','notify_message')
					return False
				user._lastTrigger = t.name
				self.doChat(network,nick)
				self.addSession(user,t).init()
				LOG('%s@%s - typed trigger: %s' % (user.user or 'UNKNOWN',user.host or 'UNKNOWN',t.trigger()),user.nickAtNetwork(),'lightgreen','lightblue','notify_message')
				return True
		return False
	
	def userIsOnFserve(self,user):
		for s in self.fserveSessions.values():
			if s.fserveSession.user == user: return True
		return False
		
	def isFserveChannel(self,network,channel):
		for t in self.triggers.values():
			if t.isVisible(channel,network): return True
		return False
		
	def getLastIndexCreation(self):
		fobj = open(os.path.join(self.savePath,'index.DT'),'r')
		last = fobj.readline().strip()
		fobj.close()
		try:
			return int(last)
		except:
			return 0
		
	def doFind(self,network,target,nick,wild):
		if not self.isFserveChannel(network, target): return None
		origWild = wild
		wild = '*'+wild.replace(' ','*').strip('*')+'*'
		wild = wild.lower()
		fobj = open(os.path.join(self.savePath,'index.DT'),'r')
		fobj.readline() #remove last index time
		line = fobj.readline().strip()
		ct=0
		matches = []
		while line:
			fname = os.path.basename(line).lower()
			if fnmatch.fnmatch(fname, wild):
				if ct < 3: matches.append(line)
				ct+=1
			line = fobj.readline().strip()
		fobj.close()
		out = [self.colorize('@[TEXT]@find: showing\x0f @[DATA]%s\x0f @[TEXT]of\x0f @[DATA]%s\x0f @[TEXT]matches\x0f@[DEL]:' % (len(matches),ct))]
		ct2=1
		for m in matches:
			tname,path = m.split(':::')
			trig = self.getTrigger(tname).trigger()
			out.append(self.colorize('@[TEXT]%s.\x0f @[DATA]%s\x0f @[DEL]-\x0f @[TEXT]Trigger\x0f@[DEL]:\x0f @[DATA]%s' % (ct2,os.path.basename(path),trig)))
			ct2+=1
		if not ct:
			self.doNotice(network, nick, '@find: No Files Found')
		else:
			for o in out: self.doNotice(network, nick, o)
		LOG('@FIND: %s found %s (%s)' % (origWild,ct,target),nick + '@' + network,'lightgreen','lightblue')
		
	def createFileIndexOld(self):
		flist = []
		size = 0
		for t in self.triggers.values():
			if not t.active(): continue
			pre = t.name + ':::'
			for root, dirs, files in os.walk(t.path(),followlinks=True): #@UnusedVariable
				reC = re.compile('(?:.'+'|.'.join(t.blacklist() or t.whitelist())+')$(?i)')
				if t.whitelist():
					for f in files:
						if reC.search(f):
							full = os.path.join(root,f)
							size += os.path.getsize(full)
							flist.append(pre + full)
				elif t.blacklist():
					for f in files:
						if not reC.search(f):
							full = os.path.join(root,f)
							size += os.path.getsize(full)
							flist.append(pre + full)
				else:
					for f in files:
						full = os.path.join(root,f)
						size += os.path.getsize(full)
						flist.append(pre + full)
		open(os.path.join(self.savePath,'index.DT'),'w').write('\n'.join(flist))
		self.indexCount = len(flist)
		self.indexSize = size
		LOG('Indexed %s files (%s)' % (self.indexCount,simpleSize(size)),'INDEX','magenta','default')
		return self.indexCount,self.indexSize
		
	def getLogPath(self,days_ago=0):
		sec = 86400*days_ago
		return self.logFile % time.strftime('%m-%d-%y',time.localtime(time.time()-sec))
		
	def log(self,message,prefix='',precolor='',color='',high=''):
		DASHBOARD.log(message,prefix,precolor,color,high)
		open(self.getLogPath(),'a').write(str(int(time.time()))  + ':' + precolor + ',' + color + ':' + prefix + '=' + message + '\n')
		
	def getLog(self):
		for x in self.readLog(self.getLogPath(1)): yield x
		d = time.localtime()
		tm = time.struct_time((d.tm_year, d.tm_mon, d.tm_mday, 0, 0, 0, d.tm_wday, d.tm_yday,d.tm_isdst))
		yield int(time.mktime(tm)),'','','NEW LOG',time.strftime('[--   %m-%d-%y   --]',tm)
		for x in self.readLog(self.getLogPath()): yield x
		
	def readLog(self,logFile):
		if not os.path.exists(logFile): return
		fobj = open(logFile,'r')
		line = fobj.readline().strip()
		
		while line:
			ts,colors,pre_msg = line.split(':',2)
			preC,msgC = colors.split(',',1)
			pre,msg = pre_msg.split('=',1)
			line = fobj.readline().strip()
			yield ts,preC,msgC,pre,msg
			
		fobj.close()
		
	def doNotice(self,network,target,message): pass
	
	def doSend(self,network,nick,path): pass
	
	def getClientNick(self,server): return ''
	
	def nickInChannel(self,nick,channel,network): return False
	
	def stopSend(self,queue): return False
	
	def nickInfo(self,nick,channel,network): return None
	
	def createFileIndex(self): pass
	
	def _getData(self,section,name,attr, atype): return None
	
	def _setData(self, section, name, attr, value): return None

def DarkTowerShutdown():
	DARKTOWER.unload()
	DASHBOARD.unload()
	return weechat.WEECHAT_RC_OK

class DarkTower(FServe):
	def __init__(self):
		FServe.__init__(self)
		self.xferListHook = None
		self.savePath = None
		self.usersPath = None
		self.savedSpeed = 0
		self.configFilePointer = None
		self.generalSectionPointer = None
		self.triggersSectionPointer = None
		self.queuesSectionPointer = None
		self.sendpoolsSectionPointer = None
		self.adManagerSectionPointer = None
		self.adsSectionPointer = None
		self.loading = True
		self.indexStart = 0
		
	def __call__(self,data,*args,**kwargs):
		method,data = data.split(':',1)
		return getattr(self, method)(data,*args,**kwargs)

	def init(self):
		if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, "DarkTowerShutdown", ""):
			weechat.prnt("",logo())
			self.savePath = os.path.join(weechat.info_get('weechat_dir',''),'darktower')
			self.usersPath = os.path.join(self.savePath,'users')
			self.logsPath = os.path.join(self.savePath,'logs')
			if not os.path.exists(self.usersPath): os.makedirs(self.usersPath)
			if not os.path.exists(self.logsPath): os.makedirs(self.logsPath)
			self.loadSettings()
			
			weechat.hook_command("darktower", "Dark Tower FServe Commands",
				"[COMMANDS]",
				"[COMMANDS DETAIL]",
				"[COMPLETION]",
				"DARKTOWER", "command_cb:")
			
			weechat.hook_signal("xfer_ended", "DARKTOWER","signal_cb:")
#			weechat.hook_signal("xfer_send_ready", "DARKTOWER","signal_cb:")
			weechat.hook_modifier("irc_in_PRIVMSG", "DARKTOWER","signalPRIVMSG_cb:")
			
		self.logFile = os.path.join(self.logsPath,'log.%s.DT')
		global DASHBOARD
		DASHBOARD = Dashboard()
		DASHBOARD.init()
		LOG('DarkTower FServe v%s ------------------ LOAD -' % SCRIPT_VERSION,'LOAD','magenta','lightgreen')
		self.load()
		FServe.init(self)
		try:
			self.checkForSends()
		except:
			traceback.print_exc()
		self.createFileIndex()
		
	def _getData(self, section, name, attr, atype):
		if atype == 'list': atype = 'string'
		wc_attr = 'config_' + atype
		cname = "darktower.%s.%s.%s" % (section,name,attr)
		pointer = weechat.config_get(cname)
		return getattr(weechat,wc_attr)(pointer)
	
	def _setData(self, section, name, attr, value):
		cname = "darktower.%s.%s.%s" % (section,name,attr)
		pointer = weechat.config_get(cname)
		weechat.config_option_set(pointer, str(value), int(not self.loading))
	
	def indexCount(self,ct=None):
		if ct == None:
			ct = weechat.config_get_plugin('indexCount')
			if not ct: return 0
			try:
				return int(ct)
			except:
				pass
		weechat.config_set_plugin('indexCount',str(ct))
	
	def indexSize(self,sz=None):
		if sz == None:
			sz = weechat.config_get_plugin('indexSize')
			if not sz: return 0
			try:
				return int(sz)
			except:
				pass
		weechat.config_set_plugin('indexSize',str(sz))
		
	def startAdTimer(self,ad):
		if ad.active() and ad.interval():
			ad.timerID = weechat.hook_timer(ad.interval()*60000, 0, 0, "DARKTOWER", "ad_timer_callback:" + ad.name)
	
	def stopAdTimer(self,ad):
		if ad.timerID:
			weechat.unhook(ad.timerID)
			ad.timerID = None
		
	def ad_timer_callback(self,name,calls_left):
		self.adManager.timerCallback(name)
		return weechat.WEECHAT_RC_OK
		
	def saveSettings(self):
		self.saveConfig()
		
	def loadSettings(self):
		self.loadConfig()
		#Triggers
		triggers = weechat.config_get_plugin('triggers').split(',')
		for t in triggers:
			if not t: continue
			t = Trigger(self,t)
			self.triggers[t.name] = t
		
		#Queues
		queues = weechat.config_get_plugin('queues').split(',')
		for q in queues:
			if not q: continue
			q = Queue(self,q)
			self.queuePool[q.name] = q
			
		#Sendpools
		sendpools = weechat.config_get_plugin('sendpools').split(',')
		for s in sendpools:
			if not s: continue
			s = Sendpool(self,s)
			self.sendpools[s.name] = s
		
		#Ads
		ads = weechat.config_get_plugin('ads').split(',')
		for a in ads:
			if not a: continue
			a = Ad(self.adManager,a)
			self.adManager.ads.append(a)
			
		self.loading = False
		
	def setSaveable(self,saveable,section_pointer):
		for a in saveable.saveAttrs:
			option = weechat.config_search_option(self.configFilePointer,section_pointer,saveable.name + '.' + a[0])
			atype = a[1]
			if atype == 'list': atype = 'string'
			wc_attr = 'config_' + atype
			value = getattr(weechat,wc_attr)(option)
			if a[1] == 'boolean':
				value = value and 'On' or 'Off'
			saveable.setSaveAttr(a[0], value)
				
	def loadConfig(self):
		self.resetConfig()
		
		self.createSaveableOptions(self.generalSectionPointer,self, 'general')
		self.createSaveableOptions(self.adManagerSectionPointer,self.adManager, 'admanager')
		triggers = queues = sendpools = ads = None
		try:
			setPath = os.path.join(self.savePath,'settings.DT')
			if os.path.exists(setPath):
				f = open(setPath,'r')
				triggers = f.readline().strip().split(',')
				queues = f.readline().strip().split(',')
				sendpools = f.readline().strip().split(',')
				ads = f.readline().strip().split(',')
				f.close()
		except:
			traceback.print_exc()
			
		triggers = triggers or weechat.config_get_plugin('triggers').split(',')
		for t in triggers: self.createSaveableOptions(self.triggersSectionPointer,Trigger, t)
		
		queues = queues or weechat.config_get_plugin('queues').split(',')
		for q in queues: self.createSaveableOptions(self.queuesSectionPointer,Queue, q)
		
		sendpools = sendpools or weechat.config_get_plugin('sendpools').split(',')
		for s in sendpools: self.createSaveableOptions(self.sendpoolsSectionPointer,Sendpool, s)
		
		ads = ads or weechat.config_get_plugin('ads').split(',')
		for a in ads: self.createSaveableOptions(self.adsSectionPointer,Ad, a)
			
		weechat.config_read(self.configFilePointer)
			
	def createSaveableOptions(self,section_pointer,saveable,name):
		if not name: return
		for a in saveable.saveAttrs:
			atype = a[1]
			if atype == 'list': atype = 'string'
			self.createOption(section_pointer, name, a[0], atype,default=str(a[3]),val=str(a[3]))
			
	def createOption(self,section_pointer,name,attr,atype,val="",default=""):
		cb = ''
		data = ''
		if attr == 'name':
			cb = 'DARKTOWER'
			data = 'config_change_cb:'
		return weechat.config_new_option(	self.configFilePointer, section_pointer, name + '.' + attr, atype,
										    "",
										    "", 0, 99999, default, val, 0,
										    "DARKTOWER", "config_check_cb:" + atype,
										    cb, data + atype,
										    "", "")
			
	def removeSaveableOptions(self,saveable):
		for a in saveable.saveAttrs:
			self.removeOption(saveable.parent, saveable.name, a[0])
					
	def removeOption(self, section, name, attr):
		cname = "darktower.%s.%s.%s" % (section,name,attr)
		pointer = weechat.config_get(cname)
		weechat.config_option_free(pointer)
		
	def createSection(self,name):
		return weechat.config_new_section(	self.configFilePointer, name, 0, 0,
																    "", "",
																    "", "",
																    "", "",
																    "", "",
																    "", "")
		
	def resetConfig(self):
		if self.configFilePointer: weechat.config_free(self.configFilePointer)
		
		self.configFilePointer = weechat.config_new("darktower", "", "")
		
		self.generalSectionPointer = self.createSection('general')
		self.adManagerSectionPointer = self.createSection('admanager')
		self.triggersSectionPointer = self.createSection('triggers')
		self.queuesSectionPointer = self.createSection('queues')
		self.sendpoolsSectionPointer = self.createSection('sendpools')
		self.adsSectionPointer = self.createSection('ads')
		
#	def fillSaveableOptions(self,saveable,section_pointer):
#		for a in saveable.saveAttrs:
#				atype = a[1]
#				if atype == 'list': atype = 'string'
#				self.createOption(section_pointer, saveable.name, a[0], atype, saveable.getSaveAttr(a[0]))
				
	def saveConfig(self):		
		#self.resetConfig()
		out = []
		
		triggers = ','.join(self.triggers.keys())
		weechat.config_set_plugin('triggers', triggers)
		out.append(triggers)
		#for t in self.triggers.values(): self.fillSaveableOptions(t, self.triggersSectionPointer)
		
		queues = ','.join(self.queuePool.keys())
		weechat.config_set_plugin('queues', queues)
		out.append(queues)
		#for q in self.queuePool.values(): self.fillSaveableOptions(q, self.queuesSectionPointer)
		
		sendpools = ','.join(self.sendpools.keys())
		weechat.config_set_plugin('sendpools', sendpools)
		out.append(sendpools)
		#for s in self.sendpools.values(): self.fillSaveableOptions(s, self.sendpoolsSectionPointer)
		
		ads = ','.join(self.adManager.adNames())
		weechat.config_set_plugin('ads', ads)
		out.append(ads)

		try:
			f = open(os.path.join(self.savePath,'settings.DT'),'w')
			f.write('\n'.join(out))
			f.close()
		except:
			debug('FAILED TO WRITE TO settings.DT')
			
		weechat.config_write(self.configFilePointer)
		weechat.command("",'/save plugins')
		
	def config_change_cb(self,data, option):
		if self.loading: return weechat.WEECHAT_RC_OK
		hdata = weechat.hdata_get("config_option")
		sectionp = weechat.hdata_pointer(hdata, option, "section")
		shdata = weechat.hdata_get("config_section")
		section = weechat.hdata_string(shdata, sectionp, "name")
		name_attr = weechat.hdata_string(hdata, option, "name")
		wc_attr = 'config_' + data
		value = getattr(weechat,wc_attr)(option)
		if not section or not '.' in name_attr: return weechat.WEECHAT_RC_OK
		name, attr = name_attr.split('.')
		if attr == 'name' and name != value:
			saveable = None
			if section == 'triggers':
				saveable = self.getTrigger(name)
				if saveable: saveable.changeName(value)
				weechat.config_set_plugin('triggers', ','.join(self.triggers.keys()))
			elif section == 'queues':
				saveable = self.getQueue(name)
				if saveable: saveable.changeName(value)
				weechat.config_set_plugin('queues', ','.join(self.queuePool.keys()))
			elif section == 'sendpools':
				saveable = self.getSendpool(name)
				if saveable: saveable.changeName(value)
				weechat.config_set_plugin('sendpools', ','.join(self.sendpools.keys()))
			else:
				return weechat.WEECHAT_RC_OK
			weechat.command("",'/save plugins darktower')
			if saveable:
				for a in saveable.saveAttrs:
					oldname = '%s.%s' % (name,a[0])
					newname = '%s.%s' % (value,a[0])
					ren_option = weechat.config_search_option(self.configFilePointer, sectionp, oldname)
					weechat.config_option_rename(ren_option, newname)
			
		#s:full_name,s:config_name,s:section_name,s:option_name,s:description,s:description_nls,s:string_values,i:min,i:max,i:null_value_allowed,i:value_is_null,i:default_value_is_null,s:type,s:value,s:default_value

		return weechat.WEECHAT_RC_OK
		
	def config_check_cb(self,data, option, value):
		if self.loading: return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED
		hdata = weechat.hdata_get("config_option")
		sectionp = weechat.hdata_pointer(hdata, option, "section")
		shdata = weechat.hdata_get("config_section")
		section = weechat.hdata_string(shdata, sectionp, "name")
		name_attr = weechat.hdata_string(hdata, option, "name")
		if data == 'boolean':
			value = value == '1' and 'On' or 'Off'
		if not section or not '.' in name_attr: return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED
		name, attr = name_attr.split('.')
		saveable = None
		if section == 'triggers':
			saveable = self.getTrigger(name)
		elif section == 'queues':
			saveable = self.getQueue(name)
		elif section == 'sendpools':
			saveable = self.getSendpool(name)
		else:
			return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED
		
		if saveable:
			check = saveable.validateData(attr,value)
			if check == True:
				return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED
			else:
				weechat.prnt('','Option error (%s.%s): ' % (section,name_attr) + check)
				return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR
		else:
			return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED
		
	def save(self):
		qpool = []
		for q in self.queuePool.values():
			qpool.append(q.toString())
		spools = []
		for s in self.sendpools.values():
			spools.append(s.toString())
		open(os.path.join(self.savePath,'queues.DT'),'w').write('\n-=-\n'.join(qpool))
		open(os.path.join(self.savePath,'sends.DT'),'w').write('\n-=-\n'.join(spools))
		DASHBOARD.updateQueues()
	
	def load(self):
		queues = open(os.path.join(self.savePath,'queues.DT'),'r').read()
		sends = open(os.path.join(self.savePath,'sends.DT'),'r').read()
		for s in sends.split('\n-=-\n'):
			s = Sendpool.fromString(s, self)
			if s:
				count = 0
				if s.name in self.sendpools:
					self.sendpools[s.name].sends = s.sends
					count = self.sendpools[s.name].sendCount()
				if count: LOG('%s: Loaded %s sends' % (s.name,count),'LOAD','magenta','default')
		for q in queues.split('\n-=-\n'):
			q = Queue.fromString(q, self)
			if q:
				if q.name in self.queuePool:
					self.queuePool[q.name].items = q.items
					count = self.queuePool[q.name].count()
				if count: LOG('%s: Loaded %s queues' % (q.name,count),'LOAD','magenta','default')
		sendDatas = self.xferCheck(direct=True)
		for s in self.sendpools.values():
			for q in reversed(s.sends):
				data = self.getSendData(q, sendDatas)
				if not data:
					LOG('%s: %s not sending - re-queued' % (s.name,q.filename()),'LOAD','magenta','yellow')
					q.queue().pushItem(q)
					s.removeSend(q)
		DASHBOARD.updateQueues()
	
	def stopSend(self,q,info=None,fd=None):
		if not fd:
			if q: info = self.getSendData(q)
			if not info: return False
			fd = info.get('sock')
		if not fd: return False
		try:
			sock = socket.fromfd(fd,socket.AF_UNIX,socket.SOCK_STREAM)
			sock.shutdown(socket.SHUT_RDWR)
			sock.close()
		except:
			traceback.print_exc()
			return False
		return True
	
	def getSendData(self,i,sendDatas=None):
		#match with queueitem
		if not sendDatas: sendDatas = self.xferCheck(direct=True)
		s = {}
		for s in sendDatas:
			if s['nick'] == i.user.nick and s['network'] == i.user.network and os.path.basename(s['fname']) == i.filename(): break
		else:
			s = {}
		return s
		
	def getSendDataMatch(self,nick,network,filewild='*'):
		#match with nick and wildcard
		sendDatas = self.xferCheck(direct=True)
		for s in sendDatas:
			if s['nick'] == nick and s['network'] == network and fnmatch.fnmatch(os.path.basename(s['fname']),filewild): break
		else:
			return None
		return s
	
	def getSendDoneData(self,ip,fname):
		#Match with IP and actual filename
		sendDatas = self.sendDoneCheck()
		for s in sendDatas:
			if s['addr'] == ip and filenamesMatch(os.path.basename(s['fname']),fname): break
		else:
			return None
		return s
	
	def getClientNick(self,server):
		return weechat.info_get('irc_nick',server)
	
	def getChannelList(self,channels=None):
		#add all current channels to a (possibly empty) list of channels in the form of #channel@network
		if not channels:
			channels = []
		else:
			channels = channels[:]
		infopointer = weechat.infolist_get('irc_server','','')
		while weechat.infolist_next(infopointer):
			network = weechat.infolist_string(infopointer,'name')
			infopointerC = weechat.infolist_get('irc_channel','',network)
			while weechat.infolist_next(infopointerC):
				channel = weechat.infolist_string(infopointerC,'name') + '@' + network
				if channel[0] in self.allowedChannelPrefixes() and not channel in channels:
					channels.append(channel)
			weechat.infolist_free(infopointerC)
		weechat.infolist_free(infopointer)
		return channels
	
	def xferCommands(self,args):
		args = args.split(' ')
		if args[0] == 'cancel' or args[0] == 'c':
			if len(args) < 2:
				weechat.prnt(weechat.current_buffer(),'Format: xfer cancel nick@network [fname_wildcard]')
				return
			try:
				nick,network = args[1].split('@',1)
			except:
				weechat.prnt(weechat.current_buffer(),'Nick format is: nick@network')
				return
			fwild = '*'
			if len(args) > 2: fwild = args[2]
			info = self.getSendDataMatch(nick,network,fwild)
			if self.stopSend(None,info=info):
				weechat.prnt(weechat.current_buffer(),'Stopping transfer connection with %s of %s.' % (info.get('nick','?'),os.path.basename(info.get('fname','?'))))
			else:
				weechat.prnt(weechat.current_buffer(),'No matching transfer found.')
			
	def doNotice(self,server,target,message):
		buf = weechat.info_get('irc_buffer',server)
		weechat.command(buf,'/notice %s %s' % (target,message))
		
	def doMessage(self,server,target,message):
		buf = weechat.info_get('irc_buffer',server)
		weechat.command(buf,'/msg %s %s' % (target,message))
		
	def doSend(self,server,nick,path,speed=15):
		try:
			self.savedSpeed = weechat.config_integer(weechat.config_get("xfer.network.speed_limit"))
			weechat.config_option_set(weechat.config_get("xfer.network.speed_limit"),str(speed),0)
			buf = weechat.info_get('irc_buffer',server)
			weechat.command(buf,'/dcc send %s %s' % (nick,path))
			return True
		except:
			traceback.print_exc()
			return False
		
	def doChat(self,server,nick):
		buf = weechat.info_get('irc_buffer',server)
		weechat.command(buf,'/dcc chat %s' % nick)

	def nickInChannel(self,nick,channel,network):
		infopointer = weechat.infolist_get('irc_nick','',network + ',' + channel + ',' + nick)
#		if weechat.infolist_next(infopointer):
#			debug(str(weechat.infolist_string(infopointer,'prefixes')))
#			debug(str(weechat.infolist_string(infopointer,'prefix')))
#			debug(str(weechat.infolist_string(infopointer,'name')))
#			debug(str(weechat.infolist_string(infopointer,'host')))
		weechat.infolist_free(infopointer)
		return bool(infopointer)
	
	def nickInfo(self,nick,channel,network):
		if channel:
			channel = ',' + channel + ','
		else:
			channel = ','
		infopointer = weechat.infolist_get('irc_nick','',network + channel + nick)
		data = {}
		if weechat.infolist_next(infopointer):
			data['prefixes'] = weechat.infolist_string(infopointer,'prefixes')
			data['prefix'] = weechat.infolist_string(infopointer,'prefix')
			host = weechat.infolist_string(infopointer,'host')
			user = ''
			if '@' in host: user,host = host.split('@',1)
			data['user'] = user
			data['host'] = host
		weechat.infolist_free(infopointer)
		return data or None
	
	def index_finished_cb(self,data, command, return_code, out, err):
		duration = time.time() - self.indexStart
		if return_code == 0:
			try:
				ct,sz = out.strip('\n').split(':',1)
				ct = int(ct)
				sz = int(sz)
				self.indexCount(ct)
				self.indexSize(sz)
				weechat.command("",'/save plugins')
				LOG('Indexed %s files (%s) in %s' % (self.indexCount(),simpleSize(sz),durationToShortText(duration,True)),'INDEX','magenta','default')
			except:
				debug('RC: ' + str(return_code) + ' OUT: ' + str(out) + ' ERR: ' + str(err))
				ct,sz = (0,0) 
		return weechat.WEECHAT_RC_OK
	
	def command_cb(self,data,bufr,args):
		if not args:
			weechat.command(weechat.current_buffer(),'/buffer DarkTower')
		if args.lower() == 'index':
			self.createFileIndex(force=True)
		elif args.lower()[:4] == 'xfer':
			self.xferCommands(args.split(' ',1)[-1])
			
		return weechat.WEECHAT_RC_OK

	def signal_cb(self,data, signal, signal_data):
		if signal == 'xfer_ended':
			return self.xferStop(signal_data)
#		elif signal == 'xfer_send_ready':
#			return self.xferStart(signal_data)
		
		return weechat.WEECHAT_RC_OK
	
	def signalPRIVMSG_cb(self,data, modifier, server, string):
		parsed = weechat.info_get_hashtable("irc_message_parse", { "message": string })
		args = parsed['arguments'].split(None,1)[-1][1:]
		text = args.strip(chr(1)).strip()
		nick = parsed['nick'] #data.split()[0].split('!')[0][1:]
		target = parsed['channel']
		if target[0] == '#':
			if text == '!list':
				#:ruuk!~ruuk25@26d9672f.12ed360d.wa.comcast.net PRIVMSG #blackforce :!list
				self.adManager.doList(nick,target,server)
			elif text[:5] == '@find':
				self.doFind(server, target, nick, text.split(' ',1)[-1])
		elif args[0] == chr(1):
			if self.checkTrigger(server,nick,text): return ''
		return string
	
	def message_cb(self,data, bufr, date, tags, displayed, highlight, prefix, message):
		return self.fserveSessions[data].messageCallback(bufr, date, tags, displayed, highlight, prefix, message)
	
#	def xferStart(self,infopointer):
#		if self.savedSpeed: weechat.config_option_set(weechat.config_get("xfer.network.speed_limit"),str(self.savedSpeed),0)
#		self.savedSpeed = 0
#		return weechat.WEECHAT_RC_OK
		
	def xferStop(self,infopointer):
		if weechat.infolist_next(infopointer):
			xtype = weechat.infolist_string(infopointer,'type')
			if not xtype == 'file_send':
				weechat.infolist_free(infopointer)
				return weechat.WEECHAT_RC_OK
			addr = weechat.infolist_string(infopointer,'address')
			path = weechat.infolist_string(infopointer,'filename')
			nick = weechat.infolist_string(infopointer,'remote_nick')
			network = weechat.infolist_string(infopointer,'plugin_id')
			data = self.getSendDoneData(addr,os.path.basename(path))
			status = data and data.get('status') or None
			for s in self.sendpools.values():
				if s.sendFinished(nick,network,path,intToIP(addr),status): break
		weechat.infolist_free(infopointer)
		
		#s:plugin_name,s:plugin_id,s:type,s:protocol,s:remote_nick,s:local_nick,s:charset_modifier,s:filename,s:size,s:start_resume,s:address,i:port
		self.save()
		return weechat.WEECHAT_RC_OK
	
	def xferCheck(self,direct=False):
		data = weechat.infolist_get('xfer','','')
		actives = []
		while weechat.infolist_next(data):
			status = weechat.infolist_string(data,'status_string')
			xtype = weechat.infolist_string(data,'type_string')
			if (status == 'active' or status == 'connecting') and (xtype == 'file_send' or xtype == 'file_recv'):
				xfer = {}
				eta = int(weechat.infolist_string(data,'eta') or 0)
				xfer['eta'] = str(eta/(3600))+':'+('0'+str((eta%3600)/60))[-2:]
				bps = int(weechat.infolist_string(data,'bytes_per_sec') or 0)
				xfer['cps'] = '%.2f' % (bps/1024.0)
				xfer['nick'] = weechat.infolist_string(data,'remote_nick')
				xfer['fname'] = weechat.infolist_string(data,'local_filename')
				xfer['size'] = weechat.infolist_string(data,'size')
				xfer['pos'] = weechat.infolist_string(data,'pos')
				xfer['addr'] = weechat.infolist_string(data,'address')
				xfer['sock'] = weechat.infolist_integer(data,'sock')
				xfer['network'] = weechat.infolist_string(data,'plugin_id')
				xfer['status'] = status
				xfer['type'] = xtype
				actives.append(xfer)
				
		weechat.infolist_free(data)
#	xxs:plugin_name,s:plugin_id,i:type,s:type_string,i:protocol,s:protocol_string,s:remote_nick,s:local_nick,s:charset_modifier,s:filename,s:size,
#	s:proxy,s:address,i:port,i:status,s:status_string,p:buffer,s:remote_nick_color,i:fast_send,i:blocksize,t:start_time,t:start_transfer,i:sock,
#	i:child_pid,i:child_read,i:child_write,p:hook_fd,p:hook_timer,s:unterminated_message,i:file,s:local_filename,i:filename_suffix,s:pos,s:ack,
#	s:start_resume,t:last_check_time,s:last_check_pos,t:last_activity,s:bytes_per_sec,s:eta
		if direct: return actives
		return weechat.WEECHAT_RC_OK
	
	def sendDoneCheck(self,direct=False):
		data = weechat.infolist_get('xfer','','')
		inactives = []
		while weechat.infolist_next(data):
			status = weechat.infolist_string(data,'status_string')
			xtype = weechat.infolist_string(data,'type_string')
			if xtype == 'file_send':
				xfer = {}
				xfer['nick'] = weechat.infolist_string(data,'remote_nick')
				xfer['network'] = weechat.infolist_string(data,'plugin_id')
				xfer['fname'] = weechat.infolist_string(data,'local_filename')
				xfer['size'] = weechat.infolist_string(data,'size')
				xfer['pos'] = weechat.infolist_string(data,'pos')
				xfer['addr'] = weechat.infolist_string(data,'address')
				xfer['status'] = status
				xfer['type'] = xtype
				inactives.append(xfer)
		weechat.infolist_free(data)
		return inactives

	def fserve_session_timer_cb(self,ID,remaining_calls):
		if ID in self.fserveSessions: self.fserveSessions[ID].timerCallback()
		return weechat.WEECHAT_RC_OK
	
	def createFileIndex(self,force=False):
		last = self.getLastIndexCreation()
		if not force and not time.time() - last > 3600: return
		LOG('Creating file index...','INDEX','magenta','default')
		self.indexStart = time.time()
		infoPath = os.path.join(self.savePath,'indexinfo.tmp')
		out = []
		for t in self.triggers.values():
			if not t.active(): continue
			out.append(t.name + '\t:\t' + t.path() + '\t:\t' + ','.join(t.whitelist())  + '\t:\t' + ','.join(t.blacklist()))
		f = open(infoPath,'w')
		f.write('\n'.join(out))
		f.close()
		script = 'python ' + os.path.join(weechat.info_get('weechat_dir',''),'python','darktower.py')
		command = '%s index "%s" "%s"' % (script,infoPath,os.path.join(self.savePath,'index.DT'))
		weechat.hook_process(command, 60000, "DARKTOWER", "index_finished_cb:")
	
	def unload(self):
		LOG('DarkTower ------------------------------ UNLOAD -','UNLOAD','magenta','lightred')

class QueueSelection:
	def __init__(self,dash):
		self.dash = dash
		self.fserve = DARKTOWER
		self.currentQueue = self.fserve.defaultQueue()
		self.item = None
		self.items = []
		self.reset()
		
	def reset(self):
		self.item = None
		self.button = 0
		self.mode = None
		return True
		
	def double(self,button,line):
		if button == 1:
			if self.clickedItem(line) == self.item:
				if self.mode == 'MOVE':
					self.reset()
					self.mode = 'HIGH'
				else:
					self.mode = 'MOVE'
			else:
				if self.mode == 'MOVE':
					self.move(self.clickedItem(line))
					return self.reset()
				else:
					self.reset()
					self.mode = 'HIGH'
		elif button == 2:
			if self.mode == 'DEL':
				if self.clickedItem(line) == self.item:
					DASHBOARD.removeQueueItem(self.item)
					self.reset()
					return True
			else:
				if self.clickedItem(line) == self.item:
					self.mode = 'DEL'
		else:
			return self.reset()
	
	def delete(self):
		DASHBOARD.removeQueueItem(self.item)
		
	def move(self,item):
		item = self.item.queue().moveItem(self.item,item)
		if item:
			LOG('Moved \'%s\' in %s for %s to pos %s' % (item.filename(),item.queue().name,item.user.nickAtNetwork(),item.queue().items.index(item)+1),'DASH','default','default','notify_none')
	
	def button1(self,line,col):
		item = self.clickedItem(line)
		if isinstance(item,Queue):
			if self.currentQueue == item.name:
				if col > 31:
					self.dash.dtmenu.setMenu('EDITQ',{'saveable':item})
					return
			self.currentQueue = item.name
			self.reset()
			self.mode = 'HIGH'
		elif self.button == 1:
			if self.double(1,line): return
		else:
			self.reset()
			self.mode = 'HIGH'
		self.button = 1
	
	def button2(self,line):
		if self.button == 2:
			if self.double(2,line): return True
		else:
			self.reset()
			self.mode = 'DEL'
		self.button = 2
	
	def button0(self,line):
		#self.reset()
		pass
		
	def clickedItem(self,line):
		if line < len(self.items):
			return self.items[line]
	
	def mouse(self,button,line,col):
		line = int(line)
		if button == 'button1':
			self.button1(line,col)
		elif button == 'button2':
			if self.button2(line): return
		else:
			self.button0(line)
			return
		self.item = self.clickedItem(line)
		
	def getHighlight(self,item):
		if self.item == item:
			return self.mode
		else:
			return ''
		
	def update(self):
		out = []
		self.items = []
		keys = self.fserve.queuePool.keys()
		if self.currentQueue in keys:
			keys.pop(keys.index(self.currentQueue))
			keys.append(self.currentQueue)
		queue = None
		for key in keys:
			queue = self.fserve.queuePool[key]
			color = 'gray'
			edit = ''
			if queue.name == self.currentQueue:
				color = 'green'
				edit = '[EDIT] '
			base = len('(%s/%s)' % (queue.count(),queue.max())) + len(edit)
			final = ('('+weechat.color('black')+'%s/%s'+weechat.color('white')+')') % (queue.count(),queue.max())
			diff = len(final) - base
			out.append(weechat.color('white,'+color) + (' ' + queue.name + ' ' + final + ' '*40)[:39+diff] + edit)
			self.items.append(queue)
		ct = 1
		if queue:
			for i in queue.items:
				self.items.append(i)
				self.items.append(i)
				high = self.getHighlight(i)
				size = simpleSize(i.size)
				size_len = len(size) + 8
				if ct > 9: size_len += 1
				if ct > 99: size_len += 1
				limit = 39 - size_len
				size = self.dash.colorize('  @[DEL](@[DATA]%s@[DEL])' % (size),high)
				nick = i.user.nickAtNetwork() + ' '*limit
				out.append(self.dash.colorize('@[DEL][@[DATA]%s@[DEL]] @[TEXT]%s%s' % (ct,nick[:limit],size),high))
				dr = squeezeFilename(i.filename(),38)
				if high == 'DEL': dr = '      RIGHT CLICK AGAIN TO DELETE      '
				out.append(self.dash.colorize(' @[DIR]%s' % (dr),high))
				ct += 1
		out.append(' ')
		self.items.append(None)
		out.append(' ')
		self.items.append(None)
		return '\n'.join(out)

class Menu:
	def makeButton(self,text,bgcolor='gray'):
		wg = weechat.color('white,'+bgcolor)
		bg = weechat.color('black,'+bgcolor)
		bgu = weechat.color('_black,'+bgcolor)
		button = bg+'['+bgu+text+wg+']'
		return button,len(text) + 2
	
class QueryContext:
	def __init__(self):
		self.resetMenu()
		self.mainItems = [weechat.color('black,white') + '      Options       ','Send File','Queue File']
		self.mainItemsKeys = ['','SEND','QUEUE']
		self.itemList = []
		self.dirBrowser = DirBrowser('/')
		self.dirBrowser.currentRelativePath = os.path.expanduser('~')
		self.nick = None
		self.network = None
		self.button = 0
		self.buttonLast = 0
		self.folderColor = weechat.color('yellow')
	
	def resetMenu(self):
		self.mode = 'MENU'
		self.function = None
		self.path = ''
		self.itemList = []
		self.button = 0
		self.buttonLast = 0
		self.normalColor = weechat.color('default')
		
	def __call__(self,data,*args,**kwargs):
		method,data = data.split(':',1)
		return getattr(self, method)(data,*args,**kwargs)

	def showMain(self):
		out = []
		for i in self.mainItems:
			out.append(i)
		return '\n'.join(out)
		
	def showFiles(self):
		self.itemList = ['..']
		show = ['..']
		dirs, files = self.dirBrowser.listDir()
		for d in dirs:
			self.itemList.append(d + '/')
			show.append(squeezeFilename(self.folderColor + ' +' + self.normalColor + d + '/ ',60))
		for f in files:
			self.itemList.append(f)
			show.append(squeezeFilename('  ' + f + ' ',60))
		path = self.dirBrowser.currentPath().rstrip('/')[-47:]
		path = path + '/' + ' '*(47-len(path))
		return '\n'.join([weechat.color('black,white') + path + ' : [CANCEL] '] + show)
			
	def showQueueNames(self):
		self.itemList = []
		for q in DARKTOWER.queuePool.values():
			self.itemList.append(q.name)
		return '\n'.join([weechat.color('black,white') + '    Choose Queue - [CANCEL]   '] + self.itemList)
	
	def mouse(self,button,line,info):
		self.nick = info.get('_buffer_localvar_channel')
		self.network = info.get('_buffer_localvar_server') or info.get('_buffer_localvar_name').rsplit('.',1)[0].split('.',1)[-1]
		line = int(line)
		if button == 'button1':
			self.button1(line)
		elif button == 'button2':
			self.button2(line)
		else:
			self.button0(line)
		
	def checkDoubleClick(self,button):
		if self.button == button and time.time() - self.buttonLast < 0.5:
			self.buttonLast = 0
			self.button = 0
			return True
		return False 
		
	def button1(self,line):
		if self.mode == 'MENU':
			if not line < len(self.mainItemsKeys): return self.button1Done()
			choice = self.mainItemsKeys[line]
			if choice == 'SEND':
				self.startSendFile()
			elif choice == 'QUEUE':
				self.startQueueFile()
		elif self.mode == 'FILE':
			line -= 1
			if line < 0: return self.resetMenu()
			if self.checkDoubleClick(1):
				if not line < len(self.itemList): return self.button1Done()
				choice = self.itemList[line]
				if choice == '..' or choice.endswith('/'):
					self.dirBrowser.changeDir(choice.strip('/'))
				else:
					self.fileChosen(choice)
		elif self.mode == 'CHOOSEQ':
			line -= 1
			if line < 0: return self.resetMenu()
			if not line < len(self.itemList): return self.button1Done()
			choice = self.itemList[line]
			self.queueChosen(choice)
		self.button1Done()
		
	def button1Done(self):
		self.button = 1
		self.buttonLast = time.time()
	
	def button2(self,line):
		self.button = 2
	
	def button0(self,line):
		self.button = 0
			
	def fileChosen(self,fname):
		path = self.dirBrowser.currentPath(fname)
		if self.function == 'SEND':
			self.doSendFile(path)
			self.resetMenu()
		elif self.function == 'QUEUE':
			self.startChooseQueue(path)
		
	def queueChosen(self,qname):
		if self.function == 'QUEUE':
			self.doAddQueue(qname)
		
	def startSendFile(self):
		self.mode = 'FILE'
		self.function = 'SEND'
		
	def doSendFile(self,path):
		if not self.nick: return
		command = '/dcc send %s %s' % (self.nick,path)
		self.doCommand(command)
		
	def startQueueFile(self):
		self.mode = 'FILE'
		self.function = 'QUEUE'
		
	def startChooseQueue(self,path):
		self.path = path
		self.mode = 'CHOOSEQ'
		
	def doAddQueue(self,qname):
		user = User(self.nick,self.network)
		queue = DARKTOWER.getQueue(qname)
		qi = QueueItem(user,self.path,qname)
		queue.addItem(qi)
		self.resetMenu()
		
	def doCommand(self,command):
		weechat.command(weechat.current_buffer(),command)
		
	def update(self):
		if self.mode == 'MENU':
			return self.showMain()
		elif self.mode == 'FILE':
			return self.showFiles()
		elif self.mode == 'CHOOSEQ':
			return self.showQueueNames()

class ListChooser(Menu):
	def __init__(self,callback,items,selected=None,multi=False):
		self.callback = callback
		self.multi = multi
		self.itemList = items
		self.selected = [False] * len(items)
		debug(str(selected))
		debug(str(items))
		if selected:
			for s in selected:
				if s in items: self.selected[items.index(s)] = True
			
		self.button = 0
		self.normalColor = weechat.color('default')
	
	def mouse(self,button,line,info,col):
		line = int(line)
		if button == 'button1':
			self.button1(line,col)
		elif button == 'button2':
			self.button2(line)
		else:
			self.button0(line)
		
	def button1(self,line,col):
		line -= 1
		if line < 0:
			if col > 50:
				return self.itemChosen(None)
			elif col > 41  and col < 48 and self.multi:
				return self.itemChosen(True)
		if not self.multi:
			return self.itemChosen(self.itemList[line])
		self.selected[line] = not self.selected[line]
				
		self.button1Done()
		
	def button1Done(self):
		self.button = 1
		self.buttonLast = time.time()
		
	def button2(self,line):
		self.button = 2
	
	def button0(self,line):
		self.button = 0
		
	def showItems(self):
		out = []
		for i,s in zip(self.itemList,self.selected):
			if s:
				out.append(weechat.color('white,blue') + i)
			else:
				out.append(i)
		wg = weechat.color('white,green')
		bg = weechat.color('black,green')
		if self.multi:
			header = wg+' Click to toggle selection:               '+bg+self.makeButton('DONE')[0]+bg+' : '+self.makeButton('CANCEL')[0]+wg+' '
		else:
			header = wg+' Choose:                                         : '+self.makeButton('CANCEL')[0]+wg+' '
		return '\n'.join([header] + out)
				
	def itemChosen(self,choice):
		if choice == True:
			choice = []
			for i,s in zip(self.itemList,self.selected):
				if s: choice.append(i)
		return self.callback(choice)
		
	def update(self):
		return self.showItems()

class PathChooser(Menu):
	def __init__(self,callback,ptype='FILE'):
		self.callback = callback
		self.type = ptype
		self.itemList = []
		self.button = 0
		self.buttonLast = 0
		self.dirBrowser = DirBrowser('/')
		self.dirBrowser.currentRelativePath = os.path.expanduser('~')
		self.folderColor = weechat.color('yellow')
		self.normalColor = weechat.color('default')
	
	def mouse(self,button,line,info,col):
		line = int(line)
		if button == 'button1':
			self.button1(line,col)
		elif button == 'button2':
			self.button2(line)
		else:
			self.button0(line)
		
	def checkDoubleClick(self,button):
		if self.button == button and time.time() - self.buttonLast < 0.5:
			self.buttonLast = 0
			self.button = 0
			return True
		return False 
		
	def button1(self,line,col):
		line -= 1
		if line < 0:
			if col > 50:
				return self.fileChosen(None)
			elif col > 39  and col < 48 and self.type == 'DIR':
				return self.dirChosen()
		if self.checkDoubleClick(1):
			if not line < len(self.itemList): return self.button1Done()
			choice = self.itemList[line]
			if choice == '..' or choice.endswith('/'):
				self.dirBrowser.changeDir(choice.strip('/'))
			else:
				if not self.type == 'DIR': self.fileChosen(choice)
		self.button1Done()
		
	def button1Done(self):
		self.button = 1
		self.buttonLast = time.time()
		
	def button2(self,line):
		self.button = 2
	
	def button0(self,line):
		self.button = 0
		
	def showFiles(self):
		self.itemList = ['..']
		show = ['..']
		dirs, files = self.dirBrowser.listDir()
		for d in dirs:
			self.itemList.append(d + '/')
			show.append(squeezeFilename(self.folderColor + ' +' + self.normalColor + d + '/ ',60))
		for f in files:
			self.itemList.append(f)
			show.append(squeezeFilename('  ' + f + ' ',60))
		selectButton = ''
		psize = 47
		if self.type == 'DIR':
			bt,sz = self.makeButton('SELECT')
			selectButton = '  ' + bt
			psize -= (sz + 2)
			
		path = self.dirBrowser.currentPath().rstrip('/')[psize*-1:]
		path = path + '/' + ' '*(psize-len(path))
		c = weechat.color('white,green')
		return '\n'.join([c+path+selectButton+c+' : '+self.makeButton('CANCEL')[0]+c+' '] + show)
	
	def file(self,choice): #@ReservedAssignment
		if self.checkDoubleClick(1):
			if not choice: return self.button1Done()
			if choice == '..' or choice.endswith('/'):
				self.dirBrowser.changeDir(choice.strip('/'))
			else:
				self.fileChosen(choice)
		self.button1Done()
				
	def fileChosen(self,fname):
		if not fname:
			return self.callback(None)
		path = self.dirBrowser.currentPath(fname)
		self.callback(path)
		
	def dirChosen(self):
		path = self.dirBrowser.currentPath()
		self.callback(path)
		
	def update(self):
		return self.showFiles()
	
class DashboardMenu(Menu):
	def __init__(self,dash):
		self.dash = dash
		self.menu = 'CLOSED'
		self.modHook = None
		self.bufferCleared = False
		self.resetMenu()
		self.items = ()
		self.button = 0
		self.buttonLast = 0
		self.subMenu = None
		self.folderColor = weechat.color('yellow')
		self.hline = weechat.config_string(weechat.config_get("weechat.look.separator_horizontal"))
		self.menus = 	{	'CLOSED':self.closed,
							'MAIN':self.main,
							'GENERAL':self.general,
							'ADMANAGER':self.adManager,
							'TRIGACTION':self.trigAction,
							'TRIGGERS':self.triggers,
							'NEWT':self.newT,
							'EDITT':self.editT,
							'SACTION':self.sendpoolsAction,
							'SENDPOOLS':self.sendpools,
							'NEWS':self.newS,
							'EDITS':self.editS,
							'NEWQ':self.newQ,
							'EDITQ':self.editQ,
							'AACTION':self.adsAction,
							'ADS':self.ads,
							'NEWA':self.newA,
							'EDITA':self.editA,
							'DIR':self.dirChooser,
							'CHANNELS':self.channelsChooser,
							'QUEUE':self.queueChooser,
							'SENDPOOL':self.sendpoolChooser
						}
		
	def resetMenu(self):
		if self.modHook:
			self.editOption('')
			weechat.unhook(self.modHook)
		self.modHook = None
		self.editOptionMode = False
		self.optionValue = None
		self.path = ''
		self.data = None
		self.items = ()
		self.button = 0
		self.buttonLast = 0
		if self.menu == 'MAIN' or self.menu == 'CLOSED':
			self.menu = 'CLOSED'
		else:
			self.menu = 'MAIN'
		self.normalColor = weechat.color('default')
		self.reloadBuffer()
		
	def setMenu(self,menu,data):
		self.resetMenu()
		self.menu = menu
		self.menus[menu](init=data)
		weechat.bar_item_update('dtmenu')
		
	def __call__(self,data,*args,**kwargs):
		method,data = data.split(':',1)
		return getattr(self, method)(data,*args,**kwargs)
	
	def mouse(self,button,line,info,col):
		if self.subMenu:
			return self.subMenu.mouse(button, line, info,col)
		line = int(line)
		if button == 'button1':
			self.button1(line)
		elif button == 'button2':
			self.button2(line)
		else:
			self.button0(line)
		
	def checkDoubleClick(self,button):
		if self.button == button and time.time() - self.buttonLast < 0.5:
			self.buttonLast = 0
			self.button = 0
			return True
		return False 
		
	def button1(self,line):
		if line == 0: return self.resetMenu()
		if not line < len(self.items): return self.menus[self.menu](line,'')
		choice = self.items[line][1]
		self.menus[self.menu](line,choice)

	def button1Done(self):
		self.button = 1
		self.buttonLast = time.time()
	
	def button2(self,line):
		self.button = 2
	
	def button0(self,line):
		self.button = 0
		
	def doCommand(self,command):
		weechat.command(weechat.current_buffer(),command)
		
	def header(self,text,msg='CANCEL'):
		button,sz = self.makeButton(msg)
		size = 29 - sz
		c = weechat.color('white,blue')
		return c + (' %s                                 ' % text)[:size]+button+c+' '
	
	def makeLongButton(self,label,color):
		blen = len(label) + 2
		left = (30-blen)/2
		right = 30 - (blen + left)
		return weechat.color(color) + self.hline*left + weechat.color('black,'+color) + '[' + weechat.color('_black,'+color) + label + weechat.color('white,'+color) + ']' + weechat.color('default,default') + weechat.color(color + ',default') + self.hline*right
	
	def reloadBuffer(self):
		if not self.bufferCleared: return
		self.dash.loadLog()
		self.bufferCleared = False
		
	def setBuffer(self,text):
		channel = ''
		network = ''
		if 'temp' in self.data:
			if 'channels' in self.data['temp']:
				chanNet = self.data['temp']['channels'].split(',')[0]
				if '@' in chanNet:
					channel,network = chanNet.split('@',1)
		weechat.buffer_clear(self.dash.buffer)
		weechat.prnt(self.dash.buffer,DARKTOWER.adManager.processTags4Weechat(text, None, network, channel))
		self.bufferCleared = True
	
	def editOption(self,val):
		self.editOptionMode = True
		self.optionValue = val
		weechat.buffer_set(weechat.current_buffer(),'input',str(val))
		weechat.buffer_set(weechat.current_buffer(),'input_pos',str(len(str(val))))
		if not self.modHook: self.modHook = weechat.hook_modifier('input_text_content', 'DASHBOARD', 'input_ext_content_mod_cb:')
	
	def getOptionEdit(self):
		return weechat.buffer_get_string(weechat.current_buffer(),'input')
	
	def editSaveable(self,line=None,choice=None,edit=False):
		saveable = self.data['saveable']
		if choice == None:
			line = self.data['line']
			color = 'white'
			error = ''
			if line < 0:
				line += 1000
				color = 'red'
				error = self.data.get('error')
				self.data['error'] = None
				
			self.items = [(self.header(self.data['header'],'CANCEL'),'')]
			for a in saveable.saveAttrs:
				size = 30 - (len(a[2]) + 3)
				disp = ' ' + a[2] + ': ' + weechat.color('green') + self.data['temp'][a[0]][:size]
				menu = self.data['menu']
				if a[4]:
					menu = a[4].upper()
				elif a[1] == 'boolean':
					menu = 'BOOLEAN'
				self.items.append((disp,menu))
			self.items.append((self.hline*30,''))
			self.items.append((self.makeLongButton('SAVE','green'),''))
			if edit:
				self.items.append((self.makeLongButton('DELETE','red'),''))
			self.items.append((self.hline*30,''))
			if error:
				self.items.append((' '*30,''))
				for l in textwrap.wrap(error, 30): self.items.append((l,''))
			if line:
				disp = self.items[line][0]
				if self.editOptionMode:
					text = self.getOptionEdit()
					if self.items[line][1] == 'IRCTEXT':
						self.setBuffer(text)
					else:
						self.reloadBuffer()
					if text != None:
						pre = self.items[line][0].split(': ',1)[0]
						size = 30 - (len(pre) + 2)
						disp = pre + ': ' + weechat.color(color == 'red' and 'black' or 'red') + text[:size]
				self.items[line] = (weechat.color('black,' + color) + disp,self.items[line][1])
			return self.makeMenu()
		old = self.data['line']
		if old and old != line:
			attrInfo = saveable.getSaveAttrInfoByIndex(old - 1)
			if attrInfo:
				text = self.getOptionEdit()
				validate = saveable.validateData(attrInfo[0],text)
				if validate == True:
					self.data['temp'][attrInfo[0]] = text
				else:
					line = old - 1000
					self.data['error'] = validate
				
		if line <= len(saveable.saveAttrs):
			self.data['line'] = line
			attrInfo = saveable.getSaveAttrInfoByIndex(line - 1)
			if attrInfo:
				text = self.data['temp'][attrInfo[0]]
				self.editOption(text)
			if line > 0 and line == old:
				sub = self.items[line][1]
				if sub == 'DIR':
					return self.dirChooser(line, choice)
				elif sub == 'CHANNELS':
					return self.channelsChooser(line, choice)
				elif sub == 'QUEUE':
					return self.queueChooser(line, choice)
				elif sub == 'SENDPOOL':
					return self.sendpoolChooser(line, choice)
				elif sub == 'BOOLEAN':
					return self.toggleBoolean(line,choice,attrInfo[0])
		if line == len(saveable.saveAttrs) + 2:
			self.data['save'](saveable)
			self.resetMenu()
		if line == len(saveable.saveAttrs) + 3:
			self.data['del'](saveable)
			self.resetMenu()	
		
	def dirChooser(self,line=None,choice=None):
		self.subMenu = PathChooser(self.pathChosen,'DIR')
		
	def pathChosen(self,path):
		del self.subMenu
		self.subMenu = None
		if path: self.editOption(path)
		
	def channelsChooser(self,line=None,choice=None):
		edit = self.getOptionEdit()
		selected = []
		if edit: selected = edit.split(',')
		channels = DARKTOWER.getChannelList(selected)
		
		self.subMenu = ListChooser(self.channelsChosen,channels,selected=selected,multi=True)
		
	def channelsChosen(self,channels):
		del self.subMenu
		self.subMenu = None
		if channels != None: self.editOption(','.join(channels))
		
	def queueChooser(self,line=None,choice=None):
		self.subMenu = ListChooser(self.itemChosen,DARKTOWER.queuePool.keys())
		
	def sendpoolChooser(self,line=None,choice=None):
		self.subMenu = ListChooser(self.itemChosen,DARKTOWER.sendpools.keys())
		
	def itemChosen(self,choice):
		del self.subMenu
		self.subMenu = None
		if choice: self.editOption(choice)

	def toggleBoolean(self,line=None,choice=None,attr=None):
		edit = self.getOptionEdit()
		if not edit: edit = 'off'
		edit = edit.lower() == 'on' and 'Off' or 'On'
		self.editOption(edit)
		if attr: self.data['temp'][attr] = edit
		
	def general(self,line=None,choice=None,init=None):
		if not self.data:
			self.data = {	'saveable':DARKTOWER,
							'line':0,
							'save':self.saveGeneral,
							'header':'General Options: ',
							'menu':'GENERAL'
						}
			self.createSaveableProxy()
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, False)
	
	def saveGeneral(self,fserve):
		fserve.updateSaveAttrsFromDict(self.data['temp'])
		fserve.saveSettings()
		
	def adManager(self,line=None,choice=None,init=None):
		if not self.data:
			self.data = {	'saveable':DARKTOWER.adManager,
							'line':0,
							'save':self.saveAdManager,
							'header':'Ad Options: ',
							'menu':'ADMANAGER'
						}
			self.createSaveableProxy()
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, False)
	
	def saveAdManager(self,adManager):
		adManager.updateSaveAttrsFromDict(self.data['temp'])
		DARKTOWER.saveSettings()
		
	def newQ(self,line=None,choice=None,edit=False,init=None):
		if not self.data:
			self.data = {	'saveable':Queue(DARKTOWER,self.uniqueName(DARKTOWER.queuePool,'NEW')),
							'line':0,
							'save':self.saveQ,
							'del':self.deleteQ,
							'header':'Queue Options: ',
							'menu':edit and 'EDITQ' or 'NEWQ'
						}
			self.createSaveableProxy(new=True)
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, edit)
	
	def createSaveableProxy(self,new=False):
		saveable = self.data['saveable']
		self.data['temp'] = saveable.getSaveAttrsAsDict(new)
	
	##--------------------------------
	## Queues	
	def editQ(self,line=None,choice=None,init=None):
		return self.newQ(line, choice,edit=True,init=init)
		
	def saveQ(self,queue):
		if not DARKTOWER.getQueue(queue.name):
			DARKTOWER.createSaveableOptions(DARKTOWER.queuesSectionPointer,queue,self.data['temp']['name'])
			DARKTOWER.queuePool[queue.name] = queue
		queue.updateSaveAttrsFromDict(self.data['temp'])
		self.dash.updateQueues()
		DARKTOWER.saveSettings()
		
	def deleteQ(self,queue):
		if queue.name in DARKTOWER.queuePool: del DARKTOWER.queuePool[queue.name]
		DARKTOWER.removeSaveableOptions(queue)
		self.dash.updateQueues()
		DARKTOWER.saveSettings()
		
	##--------------------------------
	## Triggers
	def trigAction(self,line=None,choice=None):
		if choice == None:
			self.items = [	(self.header('Trigger Action: '),''),
							('New','NEWT')
						]
			if DARKTOWER.triggers: self.items.append(('Edit','TRIGGERS'))
			return self.makeMenu()
		self.processChoice(choice)
		
	def triggers(self,line=None,choice=None):
		if choice == None:
			self.items = [(self.header('Triggers: '),'')]
			for t in DARKTOWER.triggers.values():
				self.items.append((t.name,t.name))
			return self.makeMenu()
		self.preEditT(choice)
		
	def newT(self,line=None,choice=None,edit=False,init=None):
		if not self.data:
			self.data = {	'saveable':Trigger(DARKTOWER,self.uniqueName(DARKTOWER.triggers,'NEW')),
							'line':0,
							'save':self.saveT,
							'del':self.deleteT,
							'header':'Trigger Options: ',
							'menu':'NEWT'
						}
			self.createSaveableProxy(new=True)
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, edit)
	
	def preEditT(self,choice):
		if choice:
			trig = DARKTOWER.getTrigger(choice)
			if not trig: return
			self.setMenu('EDITT',{'saveable':trig})
			choice = None
			
	def editT(self,line=None,choice=None,init=None):
		return self.newT(line, choice,edit=True,init=init)
		
	def saveT(self,trigger):
		if not DARKTOWER.getTrigger(trigger.name):
			DARKTOWER.createSaveableOptions(DARKTOWER.triggersSectionPointer,trigger,self.data['temp']['name'])
			DARKTOWER.triggers[trigger.name] = trigger
		trigger.updateSaveAttrsFromDict(self.data['temp'])
		DARKTOWER.saveSettings()
		
	def deleteT(self,trigger):
		if trigger.name in DARKTOWER.triggers: del DARKTOWER.triggers[trigger.name]
		DARKTOWER.removeSaveableOptions(trigger)
		DARKTOWER.saveSettings()
		
	##--------------------------------
	## Sendpools
	def newS(self,line=None,choice=None,edit=False,init=None):
		if not self.data:
			self.data = {	'saveable':Sendpool(DARKTOWER,self.uniqueName(DARKTOWER.sendpools,'NEW')),
							'line':0,
							'save':self.saveS,
							'del':self.deleteS,
							'header':'Sendpool Options: ',
							'menu':'NEWS'
						}
			self.createSaveableProxy(new=True)
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, edit)
	
	def preEditS(self,choice):
		if choice:
			sendpool = DARKTOWER.getSendpool(choice)
			if not sendpool: return
			self.setMenu('EDITS',{'saveable':sendpool})
			choice = None
			
	def editS(self,line=None,choice=None,init=None):
		return self.newS(line, choice,edit=True,init=init)
	
	def saveS(self,sendpool):
		if not DARKTOWER.getSendpool(sendpool.name):
			DARKTOWER.createSaveableOptions(DARKTOWER.sendpoolsSectionPointer,sendpool,self.data['temp']['name'])
			DARKTOWER.sendpools[sendpool.name] = sendpool
		sendpool.updateSaveAttrsFromDict(self.data['temp'])
		DARKTOWER.saveSettings()
		
	def deleteS(self,sendpool):
		if sendpool.name in DARKTOWER.sendpools: del DARKTOWER.sendpools[sendpool.name]
		DARKTOWER.removeSaveableOptions(sendpool)
		DARKTOWER.saveSettings()
	
	def sendpoolsAction(self,line=None,choice=None):
		if choice == None:
			self.items = [	(self.header('Sendpool Action: '),''),
							('New','NEWS')
						]
			if DARKTOWER.sendpools: self.items.append(('Edit','SENDPOOLS'))
			return self.makeMenu()
		self.processChoice(choice)
	
	def sendpools(self,line=None,choice=None):
		if choice == None:
			self.items = [(self.header('Sendpools: '),'')]
			for s in DARKTOWER.sendpools.values():
				self.items.append((s.name,s.name))
			return self.makeMenu()
		self.preEditS(choice)
	
	##--------------------------------
	## Ads
	def ads(self,line=None,choice=None):
		if choice == None:
			self.items = [(self.header('Ads: '),'')]
			for an in DARKTOWER.adManager.adNames():
				self.items.append((an,an))
			return self.makeMenu()
		self.preEditA(choice)
		
	def newA(self,line=None,choice=None,edit=False,init=None):
		if not self.data:
			self.data = {	'saveable':Ad(DARKTOWER.adManager,'NEW'), #TODO: genereate a unique name
							'line':0,
							'save':self.saveA,
							'del':self.deleteA,
							'header':'Ad Options: ',
							'menu':'NEWA'
						}
			self.createSaveableProxy(new=True)
		if init:
			self.data.update(init)
			self.createSaveableProxy()
		return self.editSaveable(line, choice, edit)
	
	def preEditA(self,choice):
		if choice:
			ad = DARKTOWER.getAd(choice)
			if not ad: return
			self.setMenu('EDITA',{'saveable':ad})
			choice = None
			
	def editA(self,line=None,choice=None,init=None):
		return self.newA(line, choice,edit=True,init=init)
	
	def saveA(self,ad):
		if not DARKTOWER.getAd(ad.name):
			DARKTOWER.createSaveableOptions(DARKTOWER.adsSectionPointer,ad,self.data['temp']['name'])
			DARKTOWER.adManager.ads.append(ad)
		ad.updateSaveAttrsFromDict(self.data['temp'])
		DARKTOWER.saveSettings()
		
	def deleteA(self,ad):
		if DARKTOWER.getAd(ad.name):
			DARKTOWER.adManager.removeAd(ad)
		DARKTOWER.removeSaveableOptions(ad)
		DARKTOWER.saveSettings()
	
	def adsAction(self,line=None,choice=None):
		if choice == None:
			self.items = [	(self.header('Ad Action: '),''),
							('New','NEWA')
						]
			if DARKTOWER.adManager.adNames(): self.items.append(('Edit','ADS'))
			return self.makeMenu()
		self.processChoice(choice)
		
	##--------------------------------	
	def uniqueName(self,pool,base):
		ct = 1
		new = base
		while True:
			if new in pool:
				new = base + str(ct)
				ct+=1
				break
			else:
				return new
		return new
			
	def closed(self,line=None,choice=None):
		if choice == None:
			#TODO: use weechat sep color as bg
			self.items = [	(weechat.color('black,red') + ' ','MAIN'),
							(weechat.color('black,red') + 'M','MAIN'),
							(weechat.color('black,red') + 'E','MAIN'),
							(weechat.color('black,red') + 'N','MAIN'),
							(weechat.color('black,red') + 'U','MAIN'),
							((weechat.color('black,red') + ' \n')*100,'MAIN')
						]
			return self.makeMenu()
		#self.processChoice(choice)
		self.menu = 'MAIN'
		
	def main(self,line=None,choice=None):
		if choice == None:
			self.items = (	(self.header('Options: ','CLOSE'),''),
							('General','GENERAL'),
							('Ad Settings','ADMANAGER'),
							('Manage Triggers','TRIGACTION'),
							('Add New Queue','NEWQ'),
							('Manage Sendpools','SACTION'),
							('Manage Ads','AACTION')
						)
			return self.makeMenu()
		self.processChoice(choice)
		
	def processChoice(self,choice):
		if not choice:
			self.resetMenu()
		
		self.menu = choice
		
	def makeMenu(self):
		out = []
		for d,k in self.items: #@UnusedVariable
			out.append(d)
		return '\n'.join(out)
	
	def update(self):
		if self.subMenu:
			return self.subMenu.update()
		out = self.menus[self.menu]()
		if not out:
			self.menu = 'MAIN'
			out = self.menus[self.menu]()
		return out
			
class XferBar(Menu):
	def __init__(self):
		self.barEndC = weechat.color('white,gray')
		self.mainC = weechat.color('default,default')
		self.highlightColor = weechat.color('default,blue')
		self.menuOn = False
		self.lastButton = 0
		self.menuColor = weechat.color('white,blue')
		self.items = []
		self.selected = None
		self.menuSizeMod = 0
		self.data = []
	
	def mouse(self,button,line,info,col):
		if button == 'button1':
			self.button1(line,col)
			self.button = 1
	
	def button1(self,line,col):
		if not self.menuOn: self.menuOn = True
		item = self.getItem(line)
		if item == False: return
		if not item: return self.menu(col)
		self.selected = self.data.index(item)
		
	def selectedItem(self):
		return self.getDataItem(self.selected)
	
	def closeMenu(self):
		self.selected = None
		self.menuOn = False

	def menu(self,col):
		item = self.selectedItem()
		if col > 2 and col < 19:
			if not item: return
			DARKTOWER.stopSend(None,fd=item.get('sock'))
			self.closeMenu()
		elif col > 21 and col < 30 + self.menuSizeMod:
			if not item: return
			nick = item.get('nick')
			network = item.get('network')
			buf = weechat.buffer_search('irc','server.' + network)
			if not buf: return
			weechat.command(buf,'/query '+nick)
			self.closeMenu()
		elif col > 32 + self.menuSizeMod:
			self.closeMenu()
		
	def getItem(self,line):
		if line < len(self.items): return self.items[line]
		return False
	
	def getDataItem(self,idx):
		if idx < len(self.data): return self.data[idx]
		return None
	
	def update(self,data,item,window):
		xferdata = DARKTOWER.xferCheck(direct=True)
		self.data = xferdata
		bars = []
		self.items = []
		ct=0
		high = ''
		menuNickAtNetwork = ''
		if not xferdata:
			self.closeMenu()
		for d in xferdata:
			high = self.mainC
			nickAtNetwork = str(d.get('nick')) + '@' + str(d.get('network'))
			if ct == self.selected:
				high = self.highlightColor
				menuNickAtNetwork = nickAtNetwork
				self.menuSizeMod = len(menuNickAtNetwork)
			color = 'red'
			if d.get('type') == 'file_recv': color = 'green'
			bar = self.barEndC + '|%s ' % self.bar(d.get('pos',0),d.get('size',0),color) +self.barEndC+'|' +high+ ' %s - %s @ %sKBps - ETA: %s' % (nickAtNetwork,os.path.basename(d['fname']),d['cps'],d['eta'])
			bars.append(bar)
			self.items.append(d)
			if ct == self.selected and self.menuOn:
				self.items.append(None)
				base = self.menuColor+ '   %s'+self.menuColor+' : %s'+self.menuColor+' : %s'
				bars.append(base % (self.makeButton('ABORT SELECTED')[0],self.makeButton('QUERY ' + menuNickAtNetwork)[0],self.makeButton('CLOSE MENU')[0]) + self.menuColor)
			ct+=1
			
		return '\n'.join(bars)
	
	def bar(self,pos,size,color,width=30):
		barwidth = width
		try:
			pos = int(pos)
			size = int(size)
		except:
			return barwidth*" "
		
		color1 = weechat.color('_white,' + color)
		color2 = weechat.color('_white,black')
		if size:
			width_per_size = (barwidth) / float(size)
			transf_chars = int(width_per_size * pos)
			non = 0 - (barwidth - transf_chars)
			prct = (size == 0) and "0.0%%" or "%.1f%%" % ((pos*100.0)/size)
			plen = len(prct)
			sides = barwidth - plen
			right = int(sides / 2)
			left = barwidth - (right + plen)
			filebar = " "*left + prct + " "*right
			part2 = ''
			if non: part2 = color2+filebar[non:]
			filebar = color1+filebar[0:transf_chars]+part2
			return filebar
		else:
			return barwidth*" "
		
class Dashboard:
	def __init__(self):
		self.buffer = None
		self.timer = None
		self.queueSelection = QueueSelection(self)
		self.queryContext = QueryContext()
		self.dtmenu = DashboardMenu(self)
		self.xferBar = XferBar()
		self.lastStatus = ''
	
	def __call__(self,data,*args,**kwargs):
		method,data = data.split(':',1)
		return getattr(self, method)(data,*args,**kwargs)
	
	def init(self):
		weechat.bar_item_new('queues', 'DASHBOARD', 'queues_cb:')
		weechat.bar_new("queues", "on", "0", "window", "", "left", "horizontal", "vertical", "40", "40", "default", "default", "default", "1", "queues")
		weechat.hook_focus("queues","DASHBOARD","queues_focus_cb:")

		weechat.bar_item_new('dtmenu', 'DASHBOARD', 'dtmenu_cb:')
		weechat.bar_new("dtmenubar", "on", "0", "window", "", "right", "horizontal", "vertical", "0", "60", "default", "default", "default", "1", "dtmenu")
		weechat.hook_focus('dtmenu','DASHBOARD','dtmenu_focus_cb:')
		
		weechat.bar_item_new('querycontext', 'DASHBOARD', 'querycontext_cb:')
		weechat.bar_new("querycontextbar", "on", "0", "window", "", "right", "horizontal", "vertical", "0", "60", "default", "default", "default", "1", "querycontext")
		weechat.hook_focus('querycontext','DASHBOARD','querycontext_focus_cb:')
		
		weechat.bar_item_new('xferbar', 'DASHBOARD', 'xferbar_cb:')
		weechat.bar_new("xferbar", "off", "0", "root", "", "top", "vertical", "horizontal", "0", "4", "default", "default", "default", "1", "xferbar")
		weechat.hook_focus('xferbar','DASHBOARD','xferbar_focus_cb:')

		self.buffer = weechat.buffer_new('DarkTower', 'DASHBOARD', 'input_cb:', 'DASHBOARD', 'close_cb:')
		
		weechat.hook_signal('buffer_opened','DASHBOARD','signal_cb:')
		weechat.hook_signal('buffer_switch','DASHBOARD','signal_cb:')
		weechat.hook_signal('buffer_closed','DASHBOARD','signal_cb:')
		
		mouseKeys = { 	"@item(queues):button1": "hsignal:queues_mouse",
         				"@item(queues):button2": "hsignal:queues_mouse",
         				"@item(dtmenu):button1": "hsignal:dtmenu_mouse",
         				"@item(dtmenu):button2": "hsignal:dtmenu_mouse",
         				"@item(querycontext):button1": "hsignal:querycontext_mouse",
         				"@item(querycontext):button2": "hsignal:querycontext_mouse",
         				"@item(xferbar):button1": "hsignal:xferbar_mouse",
         				"@item(xferbar):button2": "hsignal:xferbar_mouse"
			   			}
#		weechat.hook_hsignal("queues_mouse", "DASHBOARD", "queues_mouse_cb:");
		weechat.key_bind("mouse", mouseKeys)
		
		
		self.buffer_switch(weechat.current_buffer()) #To show if we're loading when DarkTower is visible
		
		if not self.buffer: self.buffer = weechat.buffer_search('python','DarkTower')
		
		self.timer = weechat.hook_timer(3 * 1000, 0, 0, "DASHBOARD","timer_cb:")
		weechat.command(weechat.current_buffer(),'/buffer DarkTower')
		self.loadLog()
		
	def log(self,message,prefix='',precolor='',color='',high='notify_none'):
		if not self.buffer: return
		preC = precolor and weechat.color(precolor) or ''
		msgC = color and weechat.color(color) or ''
		#weechat.prnt(self.buffer,preC + prefix + '\t' + msgC + message)
		weechat.prnt_date_tags(self.buffer,0,high,preC + prefix + '\t' + msgC + message)
	
	def loadLog(self):
		weechat.buffer_clear(self.buffer)
		for ts,precolor,color,prefix,message in DARKTOWER.getLog():
			preC = precolor and weechat.color(precolor) or ''
			msgC = color and weechat.color(color) or ''
			weechat.prnt_date_tags(self.buffer, int(ts), '', preC + prefix + '\t' + msgC + message)
	
#	def queues_mouse_cb(self,data,signal,info):
#		#print 'TTEST'
#		#print info
#		return weechat.WEECHAT_RC_OK
		
	def removeQueueItem(self,item):
		if item.queue().removeItem(item=item):
			LOG('Removed \'%s\' from %s for %s' % (item.filename(),item.queue().name,item.user.nickAtNetwork()),'DASH','default','default','notify_none')
	
	def input_ext_content_mod_cb(self,data, modifier, modifier_data, string):
		weechat.bar_item_update('dtmenu')
		return string
		
	def querycontext_focus_cb(self,data,info):
		if not info['_bar_item_name'] == 'querycontext': return info
		self.queryContext.mouse(info['_key'],int(info.get('_bar_item_line',0)),info)
		weechat.bar_item_update('querycontext')
		return info
	
	def querycontext_cb(self,data,item,window):
		return self.queryContext.update()
	
	def dtmenu_focus_cb(self,data,info):
		if not info['_bar_item_name'] == 'dtmenu': return info
		self.dtmenu.mouse(info['_key'],int(info.get('_bar_item_line',0)),info,int(info.get('_bar_item_col',0)))
		weechat.bar_item_update('dtmenu')
		return info
	
	def dtmenu_cb(self,data,item,window):
		return self.dtmenu.update()
		
	def queues_focus_cb(self,data,info):
		#debug(info['_bar_item_line'] + '@' + info['_key'])
		if not info['_bar_item_name'] == 'queues': return info
		self.queueSelection.mouse(info['_key'],int(info.get('_bar_item_line',0)),int(info.get('_bar_item_col',0)))
		weechat.bar_item_update('queues')
		return info
	
	def queues_cb(self,data,item,window):
		return self.queueSelection.update()
		
	def updateQueues(self):
		self.queueSelection.reset()
		weechat.bar_item_update('queues')
		
	def colorize(self,text,high=None):
		if high:
			if high == 'DEL':
				return weechat.color('black,red') + text.replace('@[TEXT]',weechat.color('black')).\
							replace('@[DATA]',weechat.color('black')).\
							replace('@[DEL]',weechat.color('black')).\
							replace('@[DIR]',weechat.color('black')).\
							replace('@[FILE]',weechat.color('black')).\
							replace('\x0f',weechat.color('black,red'))
			elif high == 'MOVE':
				return weechat.color('black,green') + text.replace('@[TEXT]',weechat.color('black')).\
							replace('@[DATA]',weechat.color('black')).\
							replace('@[DEL]',weechat.color('black')).\
							replace('@[DIR]',weechat.color('black')).\
							replace('@[FILE]',weechat.color('black')).\
							replace('\x0f',weechat.color('black,green'))
			else:
				return weechat.color('black,white') + text.replace('@[TEXT]',weechat.color('white')).\
							replace('@[DATA]',weechat.color('red')).\
							replace('@[DEL]',weechat.color('gray')).\
							replace('@[DIR]',weechat.color('magenta')).\
							replace('@[FILE]',weechat.color('green')).\
							replace('\x0f',weechat.color('black,white'))
		else:	
			return text.replace('@[TEXT]',weechat.color('white')).\
						replace('@[DATA]',weechat.color('red')).\
						replace('@[DEL]',weechat.color('gray')).\
						replace('@[DIR]',weechat.color('magenta')).\
						replace('@[FILE]',weechat.color('green'))
		
	def buffer_switch(self,buf):
		name = weechat.buffer_get_string(buf,'name')
		if name == 'DarkTower':
			weechat.command(buf,'/bar show queues')
			weechat.command(buf,'/bar show dtmenubar')
		else:
			weechat.command(buf,'/bar hide queues')
			weechat.command(buf,'/bar hide dtmenubar')
			btype = weechat.buffer_get_string(buf,'localvar_type')
			if btype == 'private':
				self.queryContext.resetMenu()
				weechat.bar_item_update('querycontext')
				weechat.command(buf,'/bar show querycontextbar')	
				return
		weechat.command(buf,'/bar hide querycontextbar')
					
			
	def buffer_opened(self,buf): pass
	def buffer_closed(self,buf): pass
	
	def signal_cb(self,data, signal, signal_data):
		if signal == 'buffer_switch':
			self.buffer_switch(signal_data)
		elif signal == 'buffer_opened':
			self.buffer_opened(signal_data)
		elif signal == 'buffer_closed':
			self.buffer_closed(signal_data)
			
		return weechat.WEECHAT_RC_OK
	
	def input_cb(self,data, buf, input_data):
		if input_data: DARKTOWER.command_cb(None, None, input_data)
		return weechat.WEECHAT_RC_OK

	def close_cb(self,data, buf):
		#weechat.prnt("", "Buffer '%s' will be closed!" % weechat.buffer_get_string(buffer, "name"))
		return weechat.WEECHAT_RC_OK
	
	def timer_cb(self,ID,remaining_calls):
		weechat.bar_item_update('xferbar')
		self.showStatus()
		return weechat.WEECHAT_RC_OK
	
	def xferbar_focus_cb(self,data,info):
		if not info['_bar_item_name'] == 'xferbar': return info
		self.xferBar.mouse(info['_key'],int(info.get('_bar_item_line',0)),info,int(info.get('_bar_item_col',0)))
		weechat.bar_item_update('xferbar')
		return info
	
	def xferbar_cb(self,data,item,window):
		return self.xferBar.update(data, item, window)
		
	def showStatus(self):
		highC = weechat.color('black')
		plainC = weechat.color('reset')
		out = '  Sends: '
		sends = []
		for s in DARKTOWER.sendpools.values():
			sends.append(('%s ('+highC+'%s/%s'+plainC+')') % (s.name,s.sendCount(),s.max()))
		out += '  '.join(sends)
		out += '  |  Online: '
		if DARKTOWER.fserveSessions:
			users = []
			for s in DARKTOWER.fserveSessions.values():
				users.append(highC+s.fserveSession.user.prefix+s.fserveSession.user.nickAtNetwork()+plainC)
			out += ', '.join(users)
		else:
			out += highC+'None'+plainC
		if not out == self.lastStatus:
			weechat.buffer_set(self.buffer,'title',out)
		self.lastStatus = out
		
	def unload(self):
		weechat.unhook(self.timer)

####################################################################################
##
##  Functions
##
####################################################################################
def chunks(string, size):
	return [string[i:i+size] for i in range(0, len(string), size)]

def intToIP(integer):
	try:
		integer = int(integer)
	except:
		return None
	a = integer/16777216
	b = (integer%16777216)/65536
	c = ((integer%16777216)%65536)/256
	d = ((integer%16777216)%65536)%256
	return '%s.%s.%s.%s' % (a,b,c,d)

def calculatePercent(pos,size):
	if not pos: return 0
	if not size: return 0
	try:
		pos = int(pos)
		size = int(size)
	except:
		return 0
	pct = int((pos * 100.0)/size)
	return pct

def squeezeFilename(fname,limit):
		if len(fname) <= limit: return fname
		first = int((limit/5.0)*3)
		second = (limit - (first + 3)) * -1
		return fname[:first] + '...' + fname[second:]
	
def simpleSize(b):
		if b == None: return ''
		if b < 0: return ''
		val = (b/1000)
		gig = (val/1073741)
		if gig >= 1:
			dec = ''
			rest = val - (gig*1073741)
			if gig < 10: dec = "." + str((rest/1074))[0]
			return "%s%s GB" % (gig,dec)
		meg = b/1048576
		if meg >= 1:
			dec = ''
			rest = b - (meg * 1048576)
			if meg < 10: dec = "." + str(rest/1048)[0]
			return "%s%s MB" % (meg,dec)
		k = b/1024
		if k >= 1:
			dec = ''
			rest = b - (k * 1024)
			if k < 10: dec = "."+str((rest*10)/1024)[0]
			return "%s%s KB" % (k,dec)
		return "%s B" % b

def durationToShortText(unixtime,tenths=False):
	days = int(unixtime/86400)
	if days: return '%sd' % days
	left = unixtime % 86400
	hours = int(left/3600)
	if hours: return '%sh' % hours
	left = left % 3600
	mins = int(left/60)
	if mins: return '%sm' % mins
	if tenths:
		sec = float(left % 60)
		if sec: return '%.1fs' % sec
	else:
		sec = int(left % 60)
		if sec: return '%ss' % sec
	return '0s'
	
def filenamesMatch(first,second):
	#Match files by removing non-alphanumerics first
	#TODO: use difflib if this isn't good enough
	first = re.sub('[\W_]','',first)
	second = re.sub('[\W_]','',second)
	return first == second
	
def dictToHex(d):
	vals = []
	for k,v in d.items():
		if isinstance(v,int):
			k+='I'
		elif isinstance(v,long):
			k+='L'
		elif isinstance(v,float):
			k+='F'
		else:
			k+='S'
		vals.append(k+'='+str(v))
	return binascii.hexlify('\n'.join(vals))

def hexToDict(h):
	d = {}
	for l in binascii.unhexlify(h).splitlines():
		k,v = l.split('=')
		i = k[-1]
		k = k[:-1]
		if i == 'I':
			v = int(v)
		elif i == 'L':
			v = long(v)
		elif i == 'F':
			v = float(v)
		d[k] = v
	return d

	
def logo():
	l = "\n\n"+\
		"\x19*11,11______________________\n"+\
		"\x19*11,11__\x19*09,09_\x19*01,01_\x19B@00006_\x19*15,11__\x19*01,01___\x19*15,11__\x19*15,01_\x19*09,09_\x19*@00006,@00006_\x19*11,11_______\n"+\
		"\x19*11,11__\x19*09,09_\x19*01,01__________\x19*09,09_\x19*@00006,@00006_\x19*11,11_______\n"+\
		"\x19*11,11__\x19*09,09_\x19*15,01__________\x19*09,09_\x19*@00006,@00006_\x19*11,11_______\n"+\
		"\x19*11,11___\x19*09,09_\x19*15,01________\x19*09,09_\x19*@00006,@00006_\x19*11,11________\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01______\x19*09,09_\x19*@00006,@00006_\x19*11,11_________\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01_\x19*09,09_\x19*07,07__\x19*01,01__\x19*09,09_\x19*@00006,@00006_\x19*01,01__\x19*15,11__\x19*15,01_\x19*09,09_\x19*@00006,@00006_\x19*11,11__\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01_\x19*09,09_\x19*07,07__\x19*01,01__\x19*09,09_\x19*@00006,@00006_\x19*01,01_____\x19*09,09_\x19*@00006,@00006_\x19*11,11__\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01______\x19*09,09_\x19*@00006,@00006_\x19*15,01_____\x19*09,09_\x19*@00006,@00006_\x19*11,11__\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01______\x19*09,09_\x19*@00006,@00006_\x19*15,01____\x19*09,09_\x19*@00006,@00006_\x19*11,11___\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01______\x19*09,09_\x19*@00006,@00006_\x19*01,01___\x19*09,09_\x19*@00006,@00006_\x19*11,11____\n"+\
		"\x19*11,11____\x19*09,09_\x19*01,01______\x19*09,09_\x19*@00006,@00006_\x19*07,07_\x19*01,01__\x19*09,09_\x19*@00006,@00006_\x19*11,11____\n"+\
		"\nDark Tower FServe v%s\n" % SCRIPT_VERSION +\
		"\x19*15,01ruuk (Rick Phillips)\n\n\n"
	return l
	
def externalLogo():
	l = "\x0306,06______________________\n"+\
		"\x0306,06__\x0302,02_\x0301,01_\x0301,11_\x0315,06__\x0301,01___\x0315,06__\x0315,01_\x0f\x0302,02_\x0312,11_\x0f\x0306,06_______\n"+\
		"\x0306,06__\x0302,02_\x0301,01__________\x0302,02_\x0312,11_\x0f\x0306,06_______\n"+\
		"\x0306,06__\x0302,02_\x0315,01__________\x0f\x0302,02_\x0312,11_\x0f\x0306,06_______\n"+\
		"\x0306,06___\x0302,02_\x0315,01________\x0f\x0302,02_\x0312,11_\x0f\x0306,06________\n"+\
		"\x0306,06____\x0302,02_\x0301,01______\x0302,02_\x0312,11_\x0f\x0306,06_________\n"+\
		"\x0306,06____\x0302,02_\x0301,01_\x0302,02_\x0307,07__\x0301,01__\x0302,02_\x0312,11_\x0f\x0301,01__\x0315,06__\x0315,01_\x0f\x0302,02_\x0312,11_\x0f\x0306,06__\n"+\
		"\x0306,06____\x0302,02_\x0301,01_\x0302,02_\x0307,07__\x0301,01__\x0302,02_\x0312,11_\x0f\x0301,01_____\x0302,02_\x0312,11_\x0f\x0306,06__\n"+\
		"\x0306,06____\x0302,02_\x0301,01______\x0302,02_\x0312,11_\x0f\x0315,01_____\x0f\x0302,02_\x0312,11_\x0f\x0306,06__\n"+\
		"\x0306,06____\x0302,02_\x0301,01______\x0302,02_\x0312,11_\x0f\x0315,01____\x0f\x0302,02_\x0312,11_\x0f\x0306,06___\n"+\
		"\x0306,06____\x0302,02_\x0301,01______\x0302,02_\x0312,11_\x0f\x0301,01___\x0302,02_\x0312,11_\x0f\x0306,06____\n"+\
		"\x0306,06____\x0302,02_\x0301,01______\x0302,02_\x0312,11_\x0f\x0307,07_\x0301,01__\x0302,02_\x0312,11_\x0f\x0306,06____\n "+\
		"\nDark Tower FServe 4 WeeChat v%s\n" % SCRIPT_VERSION +\
		"\x0315,01ruuk (Rick Phillips)\n \n \n "

	return l

def getServerList():
	infolist = weechat.infolist_get('irc_server','','')
	names = []
	while weechat.infolist_next(infolist):
		names.append(weechat.infolist_string(infolist, 'name'))
	weechat.infolist_free(infolist)
	return names

def createFileIndexProcess():
	f = open(sys.argv[2],'r')
	data = f.read()
	f.close()
	trigs = []
	for l in data.splitlines():
		trigs.append(l.split('\t:\t'))
	flist = [str(int(time.time()))]
	size = 0
	for t,path,whitelist,blacklist in trigs:
		if whitelist: whitelist = whitelist.split(',')
		if blacklist: blacklist = blacklist.split(',')
		pre = t + ':::'
		for root, dirs, files in os.walk(path,followlinks=True): #@UnusedVariable
			reC = re.compile('(?:.'+'|.'.join(blacklist or whitelist)+')$(?i)')
			if whitelist:
				for f in files:
					if reC.search(f):
						full = os.path.join(root,f)
						s = getFileSize(full)
						if s:
							size += s
							flist.append(pre + full)
			elif blacklist:
				for f in files:
					if not reC.search(f):
						full = os.path.join(root,f)
						s = getFileSize(full)
						if s:
							size += s
							flist.append(pre + full)
			else:
				for f in files:
					full = os.path.join(root,f)
					s = getFileSize(full)
					if s:
						size += s
						flist.append(pre + full)
	open(sys.argv[3],'w').write('\n'.join(flist))
	indexCount = len(flist)
	indexSize = size
	print str(indexCount)+':'+str(indexSize)

def getFileSize(file_path):
	try:
		return os.path.getsize(file_path)
	except:
		return 0
		
####################################################################################
##
##  Startup
##
####################################################################################
DASHBOARD = None
def LOG(message,prefix='',color='',precolor='',high=''):
	DARKTOWER.log(message,prefix,color,precolor,high)
	
if __name__ == "__main__":
	if len(sys.argv) > 3 and sys.argv[1] == 'index':
		createFileIndexProcess()
	else:
		import_ok = True

		try:
			import weechat #@UnresolvedImport
		except:
			print("This script must be run under WeeChat.")
			print("Get WeeChat now at: http://www.weechat.org/")
			import_ok = False
	
		def debug(nothing): pass
		DARKTOWER = DarkTower()
		DARKTOWER.init()
		import pybuffer
		debug = pybuffer.debugBuffer(globals(), "debug")
	
		