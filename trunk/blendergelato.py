#!BPY
#coding=utf-8

"""
Name: 'Blender Gelato'
Blender: 246
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato(TM)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.18n'
__url__ = ['http://code.google.com/p/blendergelato/source/browse/trunk/blendergelato.py']
__bpydoc__ = """\
Blender(TM) to NVIDIA Gelato(TM) scene converter
"""

# NVIDIA Gelato(TM) Exporter
#
# Original By: Mario Ambrogetti
# Date:        Sat, 23 Aug 2008 09:56:48 +0200
#
# ***** BEGIN GPL LICENSE BLOCK *****
#
# Script copyright (C) Mario Ambrogetti
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****

import Blender
import sys, os, shutil, subprocess
import datetime, fnmatch, uuid
import math, copy, re
import tempfile, ctypes
import getpass, socket
import xml.dom.minidom

#import pychecker.checker

WINDOWS = (sys.platform[:3] == 'win')

try:
	import xml.dom.ext
	USE_XML_DOM_EXT = True
except:
	USE_XML_DOM_EXT = False

class GelatoError(Exception):
	def __init__(self, message):
		self.message = message

	def __str__(self):
		return self.message

class EnumType(object):
	def __init__(self, *args):
		self.names = list(args)
		for idx, name in enumerate(self.names):
			setattr(self, name, idx)

	def __len__(self):
		return len(self.names)

	def __iter__(self):
		return enumerate(self.names)

	def __contains__(self, item):
		return hasattr(self, item)

	def __getitem__(self, key):
		if (type(key) is int):
			return self.names[key]
		return getattr(self, key)

	def __str__(self):
		return str([(self.names[idx], idx) for idx in xrange(len(self.names))])

	def has_key(self, key):
		return self.__contains__(key)

class OpenTempRename(object):
	__slots__ = ['filename', 'tmpname', 'fd']

	def __init__(self, filename, mode = 'r', bufsize = -1):
		"""
		Open unique temporary filename.
		It will be renamed to true name and destroyed as soon as it is closed.
		"""

		self.filename = filename
		dir = os.path.dirname(filename)
		(base, ext) = os.path.splitext(filename)

		(handle, self.tmpname) = tempfile.mkstemp(ext, 'gelato', dir)

		self.fd = os.fdopen(handle, mode, bufsize)

	def __del__(self):
		try:
			self.fd.close()

			filename_bak = self.filename + ('.bak' if WINDOWS else '~')

			if (WINDOWS and os.path.exists(filename_bak)):
				try:
					os.unlink(filename_bak)
				except:
					pass
			try:
				os.rename(self.filename, filename_bak)
			except:
				pass

			if (not WINDOWS):
				prevmask = os.umask(0)
				os.umask(prevmask)
				os.chmod(self.tmpname, (0777 - prevmask) & 0666)

			os.rename(self.tmpname, self.filename)

		except:
			sys.excepthook(*sys.exc_info())

class ProgressBar(object):
	__slots__ = ['width', 'count_min', 'count_max', 'message', \
		'length', 'buffer', 'convert', 'middle', \
		'enable_percent', 'percent', 'first',]

	def __init__(self, width):
		"""
		Progress bar for Blebder's GUI or ASCII-art
		"""

		self.width = (2 if (width < 2) else width - 2)

		self.setup()

	def setup(self, count_min = 0, count_max = 0, message = None, count_default = 0, enable_percent = True):
		self.count_min = min(count_min, count_max)
		self.count_max = max(count_min, count_max)

		self.length = count_max - count_min
		if (self.length < 1):
			self.length = 1

		self.convert = 1.0 / float(self.length)

		self.middle = self.width / 2

		self.enable_percent = (enable_percent if (self.width > 3) else False)

		self.message = (message if (message) else '')

		self.first = (True if (self.message) else False)

		self.update(count_default)

		if (INTERACTIVE):
			Blender.Window.DrawProgressBar(0.0, '')

	def update(self, value = 0):
		amount  = clamp(value, self.count_min, self.count_max)

		self.percent = (amount - self.count_min) * self.convert

		mark  = int(self.width * self.percent)
		space = self.width - mark

		if (mark == 0):
			buf = "[%s]" % ('-' * space)
		elif (space == 0):
			buf = "[%s]" % ('=' * mark)
		else:
			buf = "[%s>%s]" % ('=' * (mark - 1), '-' * space)

		if (self.enable_percent):

			num = "%02d%%" % (self.percent * 100)

			l = len(num)
			a = l / 2
			b = a + (l % 2)

			self.buffer = ''.join([buf[0:self.middle-b+1], num, buf[self.middle+a+1:]])
		else:
			self.buffer = buf

	def finish(self):
		if (INTERACTIVE):
			Blender.Window.DrawProgressBar(0.0, '')
		else:
			print

	def __str__(self):
		return self.buffer

	def __call__(self, value):
		"""
		Write to stdout and print a carriage return first
		"""

		self.update(value)

		if (INTERACTIVE):
			Blender.Window.DrawProgressBar(self.percent, self.message)
		else:
			if (self.first):
				print self.message
				self.first = False

			sys.stdout.write('\r')
			sys.stdout.write(self.buffer)
			sys.stdout.flush()

# GUI

class GUI_Base(type):

	__registry = {}
	__count = 0

	x0 = 10	# start cursor x
	y0 = 10	# start cursor y

	x = x0	# cursor x
	y = y0	# cursor y

	h = 22	# height button
	m = 10	# margin button
	s = 30	# step y

	step_x = 20 # scroll sep x
	step_y = 20 # scroll sep y

	offset_x = 0 # offset scroll x
	offset_y = 0 # offset scroll y

	def __call__(self, group_name, *args, **kwargs):
		obj = type.__call__(self, group_name, *args, **kwargs)

		GUI_Base.__count += 1
		if (GUI_Base.__count > 16381):
			GUI_Base.__count = 1

		setattr(obj, 'event',      GUI_Base.__count)
		setattr(obj, 'group_name', group_name)

		self.__registry.setdefault(group_name, []).append(obj)

		return obj

	@staticmethod
	def registry(group_name = None):
		if (group_name is None):
			return GUI_Base.__registry
		ty = type(group_name)
		if (ty is str):
			return GUI_Base.__registry[group_name]
		if (ty is list):
			slist = []
			for (k, d) in GUI_Base.__registry.iteritems():
				if k in group_name:
					slist.extend(d)
			return slist
		raise TypeError

	@staticmethod
	def inc_x(i = 0):
		GUI_Base.x += i

	@staticmethod
	def inc_y(i = 0):
		GUI_Base.y += i

	@staticmethod
	def home():
		GUI_Base.x = GUI_Base.x0 + GUI_Base.offset_x
		GUI_Base.y = GUI_Base.y0 + GUI_Base.offset_y

	@staticmethod
	def home_reset():
		GUI_Base.offset_x = 0
		GUI_Base.offset_y = 0

	@staticmethod
	def home_down():
		GUI_Base.offset_y += GUI_Base.step_y
		if (GUI_Base.offset_y > 0):
			GUI_Base.offset_y = 0

	@staticmethod
	def home_up():
		GUI_Base.offset_y -= GUI_Base.step_y

	@staticmethod
	def home_right():
		GUI_Base.offset_x += GUI_Base.step_x
		if (GUI_Base.offset_x > 0):
			GUI_Base.offset_x = 0

	@staticmethod
	def home_left():
		GUI_Base.offset_x -= GUI_Base.step_x

	@staticmethod
	def line_feed(gap = True):
		GUI_Base.x = GUI_Base.x0 + GUI_Base.offset_x
		GUI_Base.inc_y(GUI_Base.s if gap else GUI_Base.h)

	@staticmethod
	def blank(offset_x = 0):
		GUI_Base.inc_x(GUI_Base.m + offset_x)

class GUI_Value(object):
	__slots__ = ['event', 'group_name', 'name', 'default', 'func', 'help', 'sep', '_val', '_global_name']

	__metaclass__ = GUI_Base

	def __new__(cls, *args, **kwargs):

		obj = object.__new__(cls)

		obj.name = args[1]

		obj.func    = kwargs.get('func',    None)
		obj.help    = kwargs.get('help',    '')
		obj.sep     = kwargs.get('sep',     GUI_Base.m)
		obj.default = kwargs.get('default', None)

		obj._val = obj.default
		obj._global_name = 'GLOBAL_GUI_' + str(uuid.uuid1().hex).upper()

		return obj

	@apply
	def internal_val():
		def fget(self):
			if (globals().has_key(self._global_name)):
				return globals()[self._global_name].val
			return self._val

		def fset(self, value):
			if (globals().has_key(self._global_name)):
				globals()[self._global_name].val = value
			else:
				self._val = value

		return property(**locals())

	val = internal_val

	@property
	def internal_type(self):
		if (globals().has_key(self._global_name)):
			return type(globals()[self._global_name].val)
		else:
			return type(self._val)

	def setdefault(self):
		self.val = self.default

	def draw(self):
		raise NotImplementedError('class "%s" misses method' % self.__class__)

class GUI_Line(GUI_Value):

	@staticmethod
	def draw(color, size, offset_x, offset_y, width, gap = True):

		Blender.BGL.glColor3fv(color)
		Blender.BGL.glLineWidth(size)

		Blender.BGL.glBegin(Blender.BGL.GL_LINE_LOOP)
		Blender.BGL.glVertex2i(GUI_Base.x + offset_x, GUI_Base.y + offset_y)
		Blender.BGL.glVertex2i(GUI_Base.x + offset_x + width, GUI_Base.y + offset_y)
		Blender.BGL.glEnd()

		if (gap):
			GUI_Base.inc_x(width + GUI_Base.m)

class GUI_Rect(GUI_Value):

	@staticmethod
	def draw(color, x, y, width, height, gap = True):

		Blender.BGL.glColor3fv(color)
		Blender.BGL.glRecti(GUI_Base.x + x, GUI_Base.y + y, GUI_Base.x + x + width, GUI_Base.y + y + height)

		if (gap):
			GUI_Base.inc_x(width + GUI_Base.m)

class GUI_Text(GUI_Value):

	@staticmethod
	def draw(color, string, width, offset_x = 0, offset_y = 0, auto = False):

		Blender.BGL.glColor3fv(color)
		Blender.BGL.glRasterPos2i(GUI_Base.x + offset_x, GUI_Base.y + offset_y)

		w = Blender.Draw.Text(string)
		GUI_Base.inc_x(w if auto else width + GUI_Base.m)

class GUI_Button(GUI_Value):
	__slots__ = ['string', 'width']

	def __init__(self, group_name, name, string, width, **kwargs):

		self.string = string
		self.width  = width

	def draw(self):

		if (self.func is None):
			Blender.Draw.PushButton(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.help)
		else:
			Blender.Draw.PushButton(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class GUI_Toggle(GUI_Value):
	__slots__ = ['string', 'width']

	def __init__(self, group_name, name, string, width, **kwargs):

		self.string = string
		self.width  = width

	def draw(self, value = None):

		if (value is not None):
			self.val = value

		if (self.func is None):
			globals()[self._global_name] = Blender.Draw.Toggle(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.help)
		else:
			globals()[self._global_name] = Blender.Draw.Toggle(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class GUI_String(GUI_Value):
	__slots__ = ['string', 'width', 'length']

	def __init__(self, group_name, name, string, width, length, **kwargs):

		self.string = string
		self.width  = width
		self.length = length

	def draw(self, value = None):

		if (value is not None):
			self.val = value

		if (self.func is None):
			globals()[self._global_name] = Blender.Draw.String(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.length, self.help)
		else:
			globals()[self._global_name] = Blender.Draw.String(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.length, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class GUI_Number(GUI_Value):
	__slots__ = ['string', 'width', 'min', 'max']

	def __init__(self, group_name, name, string, width, min, max, **kwargs):

		self.string = string
		self.width  = width
		self.min = min
		self.max = max

	def draw(self, value = None):

		if (value is not None):
			self.val = value

		if (self.func is None):
			globals()[self._global_name] = Blender.Draw.Number(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.min, self.max, self.help)
		else:
			globals()[self._global_name] = Blender.Draw.Number(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.min, self.max, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class GUI_Slider(GUI_Value):
	__slots__ = ['string', 'width', 'min', 'max']

	def __init__(self, group_name, name, string, width, min, max, **kwargs):

		self.string = string
		self.width  = width
		self.min = min
		self.max = max

	def draw(self, value = None):

		if (value is not None):
			self.val = value

		if (self.func is None):
			globals()[self._global_name] = Blender.Draw.Slider(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.min, self.max, 0, self.help)
		else:
			globals()[self._global_name] = Blender.Draw.Slider(self.string, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.min, self.max, 0, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class GUI_Menu(GUI_Value):
	__slots__ = ['width', 'menu', '_idx2data', '_name2idx']

	def __make_menu(self, title, options):
		slist = []
		self._idx2data = {}
		self._name2idx = {}

		if (title):
			slist.append('%s %%t' % title)

		if (options):
			for idx, (name, data) in enumerate(options):
				slist.append('|%s %%x%d' % (name, idx))
				self._idx2data[idx]  = data
				self._name2idx[name] = idx

		self.menu = ''.join(slist)

		if (not globals().has_key(self._global_name)):
			self.setdefault()

	def __init__(self, group_name, name, width, title = None, options = None, **kwargs):

		self.width = width
		self.__make_menu(title, options)

	@apply
	def val():
		def fget(self):
			if (hasattr(self, '_idx2data')):
				return self._idx2data.get(self.internal_val)
			return self.default

		def fset(self, value):
			if (value is None):
				self.internal_val = 0
				return
			if (hasattr(self, '_name2idx')):
				self.internal_val = self._name2idx.get(value, 0)

		return property(**locals())

	def draw(self, title = None, options = None):

		if (not ((title is None) and (options is None))):
			self.__make_menu(title, options)

		if (self.func is None):
			globals()[self._global_name] = Blender.Draw.Menu(self.menu, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.help)
		else:
			globals()[self._global_name] = Blender.Draw.Menu(self.menu, self.event, GUI_Base.x, GUI_Base.y, self.width, GUI_Base.h, self.internal_val, self.help, self.func)

		GUI_Base.inc_x(self.width + self.sep)

class Sbase(object):
	verbose = 1
	parameter_width = 210
	button_default_space = 550
	button_default_width = 100
	togle_enable_width = 130
	string_width = 410

	literals = EnumType('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
	types    = EnumType('surface', 'displacement', 'volume', 'light', 'generic')

	color_text    = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.0, 0.0, 0.0])
	color_evident = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [1.0, 1.0, 0.8])

	# ${name[:digits]}
	re_variables = re.compile('(?<!\$)\$\{([a-zA-Z_]\w*)(?:\:(\d+))?\}')

	@staticmethod
	def re_function(matchobj):
		idx = matchobj.lastindex
		if (idx >= 1):
			name = matchobj.group(1)

			# ${frame[:digits]}
			if (name == 'frame'):
				frame = Blender.Get('curframe')
				if (idx >= 2):
					digits = int(matchobj.group(2))
					return "%0*d" % (digits, frame)

				return str(frame)

		return matchobj.group(0)

	@staticmethod
	def parse_variables(string):
		return re.sub(Sbase.re_variables, Sbase.re_function, string)

class Shader(object):

	class Parameter(object):
		__slots__ = ['type', 'default', 'type_name', 'name', '_val', '_change', '_gui_parameter']

		def __init__(self, type, default, type_name, name):
			self.type      = type
			self.default   = default
			self.type_name = type_name
			self.name      = name

			self._val    = default
			self._change = False

			self._gui_parameter = None

		def __deepcopy__(self, memo = {}):
			new_parameter = Shader.Parameter.__new__(Shader.Parameter)
			memo[id(self)] = new_parameter

			for attr_name in self.__slots__:

				if (attr_name == '_gui_parameter'):
					value = None
				else:
					value = getattr(self, attr_name)

				setattr(new_parameter, attr_name, value)

			return new_parameter

		@property
		def change(self):
			return self._change

		@apply
		def val():
			def fget(self):
				return self._val

			def fset(self, value):
				self._change = True
				self._val    = value

			return property(**locals())

		def setdefault(self):
			self._change = False
			self._val    = self.default

		def cb_parameter(self, event, val):
			self.val = val

		def draw(self):
			if (self._gui_parameter is None):
				help = self.type_name + ' ' + self.name
				if (self.default):
					help += ' (default: %s)' % self.default

				self._gui_parameter = GUI_String('shader', None, self.name + ': ', Sbase.parameter_width, 128, func = self.cb_parameter, help = help)

			self._gui_parameter.draw(self.val)

	__slots__ = ['filename', 'nameid', 'type', 'name', 'parameters', \
		'enable_sss', 'sss', 'enable_shadow', 'shadow', \
		'_gui_default', '_gui_enable_sss', '_gui_sss', \
		'_gui_enable_shadow', '_gui_shadow']

	def __init__(self, filename = None, nameid = None):

		self._gui_default       = None
		self._gui_enable_sss    = None
		self._gui_sss           = None
		self._gui_enable_shadow = None
		self._gui_shadow        = None

		self.setup(filename, nameid)

	def setup(self, filename, nameid):

		self.filename = filename
		self.nameid = nameid

		self.parameters = {}
		self.type = None
		self.name = None

		self.__setdefault()

		if (filename and (not self.parse_file())):
			raise GelatoError, 'Invalid shader'

	def __setdefault(self):
		self.enable_sss    = False
		self.sss           = 'diffusefile'
		self.enable_shadow = True
		self.shadow        = 'shadowname'

	def __deepcopy__(self, memo = {}):

		new_shader = Shader.__new__(Shader)
		memo[id(self)] = new_shader

		for attr_name in self.__slots__:

			if (attr_name in ['_gui_default', '_gui_enable_sss', '_gui_sss', '_gui_enable_shadow', '_gui_shadow']):
				value = None
			elif (attr_name == 'parameters'):
				value = {}
				for key, data in self.parameters.iteritems():
					value[key] = copy.deepcopy(data)
			else:
				value = getattr(self, attr_name)

			setattr(new_shader, attr_name, value)

		return new_shader

	def __len__(self):
		return len(self.parameters)

	def __iter__(self):
		return enumerate(self.parameters.iterkeys())

	def __getitem__(self, key):
		return self.parameters[key].val

	def __setitem__(self, key, value):
		self.parameters[key].val = str(value)

		if (INTERACTIVE):
			Blender.Draw.Redraw(1)

	def __str__(self):
		if ((self.type is None) or (not self.name)):
			if (Sbase.verbose > 1):
				print 'Error: null shader'
			return ''

		slist = []
		for (name, par) in self.parameters.iteritems():

			# skip if no change

			if (not par.change):
				continue

			ty = par.type
			val = par.val.strip()

			# float

			if (ty is Sbase.literals.float):

				try:
					slist.append('Parameter ("float %s", %s)\n' % (name, float(val)))

				except ValueError:
					if (Sbase.verbose > 1):
						print 'Error: parameter not valid "%s"' % val
					continue
			# string

			elif (ty is Sbase.literals.string):

				slist.append('Parameter ("string %s", "%s")\n' % (name, Sbase.parse_variables(val)))

			# color, point, vector, normal

			elif (ty in [Sbase.literals.color, Sbase.literals.point, Sbase.literals.vector, Sbase.literals.normal]):

				lpar = val.split(' ')

				l = len(lpar)
				if (l == 1):
					slist.append('Parameter ("%s %s", %s)\n' % (Sbase.literals[ty], name, val))
				elif (l == 3):
					slist.append('Parameter ("%s %s", (%s))\n' % (Sbase.literals[ty], name, ', '.join(lpar)))
				else:
					if (Sbase.verbose > 1):
						print 'Error: parameter not valid "%s"' % val
					continue

			# TODO matrix

			else:
				if (Sbase.verbose > 1):
					print 'Error: unknow parameter "%s"' % name

		ty = self.type

		# Shader: surface, displacement, volume, generic

		if (ty in [Sbase.types.surface, Sbase.types.displacement, Sbase.types.volume, Sbase.types.generic]):
			slist.append('Shader ("%s", "%s")\n' % (Sbase.types[ty], self.name))

		# Shader: light

		elif (ty is Sbase.types.light):
			slist.append('Light ("%s", "%s")\n' % (self.nameid, self.name))
		else:
			if (Sbase.verbose > 1):
				print 'Error: unknow type shader "%s"' % Sbase.types[ty]
			return ''

		return ''.join(slist)

	def setdefault(self):
		self.__setdefault()

		for par in self.parameters.itervalues():
			par.setdefault()

	def cb_button_default(self, event, val):
		ret = Blender.Draw.PupMenu('Default values, continue ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		self.setdefault()

	def cb_enable_sss(self, event, val):
		self.enable_sss = val

	def cb_sss(self, event, val):
		self.sss = val

	def cb_enable_shadow(self, event, val):
		self.enable_shadow = val

	def cb_shadow(self, event, val):
		self.shadow = val

	def draw(self):
		x = GUI_Base.x

		GUI_Text.draw(Sbase.color_text,    'Shader type ', 0, 2, 6, True)
		GUI_Text.draw(Sbase.color_evident, '"%s"' % Sbase.types[self.type], 0, 2, 6, True)
		GUI_Text.draw(Sbase.color_text,    ' name ', 0, 2, 6, True)
		GUI_Text.draw(Sbase.color_evident, '"%s"' % self.name, 0, 2, 6, True)

		GUI_Base.x = x + Sbase.button_default_space

		if (self._gui_default is None):
			self._gui_default = GUI_Button('shader', None, 'Default', Sbase.button_default_width, func = self.cb_button_default, help = 'Default values')

		self._gui_default.draw()

		GUI_Base.line_feed()

		i = 0
		for name in sorted(self.parameters.iterkeys(), reverse=True):

			self.parameters[name].draw()

			i += 1
			if (i > 2):
				i = 0
				GUI_Base.line_feed()

	def draw_sss(self):
		if (self._gui_enable_sss is None):
			self._gui_enable_sss = GUI_Toggle('shader', None, 'Enable SSS', Sbase.togle_enable_width, func = self.cb_enable_sss, help = 'Enable SubSurface Scattering')

		if (self._gui_sss is None):
			self._gui_sss = GUI_String('shader', None, 'parameter: ', Sbase.string_width, 200, func = self.cb_sss, help = 'Name of parameter containing diffuse file from the first SSS pass')

		self._gui_enable_sss.draw(self.enable_sss)

		if (self._gui_enable_sss.val):
			self._gui_sss.draw(self.sss)

	def gui_shadow(self):
		if (self._gui_enable_shadow is None):
			self._gui_enable_shadow = GUI_Toggle('shader', None, 'Enable shadow', Sbase.togle_enable_width, func = self.cb_enable_shadow, help = 'Enable shadow')

		if (self._gui_shadow is None):
			self._gui_shadow = GUI_String('shader', None, 'parameter: ', Sbase.string_width, 200, func = self.cb_shadow, help = 'Name of parameter containing the name of the shadow map')

		self._gui_enable_shadow.draw(self.enable_shadow)

		if (self._gui_enable_shadow.val):
			self._gui_shadow.draw(self.shadow)

	def parse_file(self):
		global CMD_MASK

		# open file

		cmd = CMD_MASK % (GSOINFO, self.filename)

		try:
			fcmd = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).stdout
		except:
			if (Sbase.verbose > 0):
				sys.excepthook(*sys.exc_info())
				print 'Error: command "%s"' % cmd
			return False

		# read first line

		line = fcmd.readline().strip()

		try:
			(ty, name) = line.split(' ')
		except ValueError:
			return False

		if (not Sbase.types.has_key(ty)):
			if (Sbase.verbose > 1):
				print 'Error: unknow shader type "%s" name "%s"' % (ty, name)
			return False

		# shader and name type

		self.type = Sbase.types[ty]
		self.name = name

		i = 0
		for line in fcmd:
			elements = line.strip().split(' ')

			l = len(elements)
			if (l == 0):
				continue

			# delete output

			if (elements[0] == 'output'):
				del elements[0]
				l -= 1
				if (l == 0):
					continue

			if (not Sbase.literals.has_key(elements[0])):
				if (Sbase.verbose > 1):
					print 'Error: unknow parameter type "%s"' % elements
				continue

			par_name = None
			par_obj  = None

			lit = Sbase.literals[elements[0]]

			# float

			if ((lit is Sbase.literals.float) and (l >= 3)):
				par_name = elements[1]
				par_obj  = self.Parameter(lit, elements[2], Sbase.literals[lit], par_name)

			# string

			elif ((lit is Sbase.literals.string) and (l >= 3)):
				par_name = elements[1]
				par_obj  = self.Parameter(lit, elements[2][1:-1], Sbase.literals[lit], par_name)

			# color, point, vector, normal

			elif ((lit in [Sbase.literals.color, Sbase.literals.point, Sbase.literals.vector, Sbase.literals.normal]) and (l >= 3)):
				val = elements[2]
				try:
					if ((l >= 7) and (elements[2] == '[' and elements[6] == ']')):
						val = '%s %s %s' % (elements[3], elements[4], elements[5])
				except:
					pass

				par_name = elements[1]
				par_obj  = self.Parameter(lit, val, Sbase.literals[lit], par_name)

			# TODO matrix

			if ((par_name is None) or (par_obj is None)):
				if (Sbase.verbose > 1):
					print 'Error: unknow parameter "%s"' % elements
					continue

			self.parameters[par_name] = par_obj
			i += 1

		fcmd.close()

		return True

	def toxml(self, document, root):
		if (not self.filename):
			return False

		# file

		(directory, filename) = os.path.split(self.filename)

		el = document.createElement('file')
		root.appendChild(el)
		el.appendChild(document.createTextNode(filename))
		el.setAttribute('directory', directory)

		# nameid

		if (self.nameid):
			el = document.createElement('nameid')
			root.appendChild(el)
			el.appendChild(document.createTextNode(self.nameid))

		# shader's parameter

		for name, par in self.parameters.iteritems():
			if (not par.change):
				continue

			el = document.createElement('parameter')
			root.appendChild(el)
			el.setAttribute('name', name)

			el.appendChild(document.createTextNode(par.val))

		return True

	def fromxml(self, root):

		# file

		el = root.getElementsByTagName('file')
		if (len(el) == 0):
			return False

		dfile = el[0]
		dfile.normalize()

		filename = dfile.firstChild.data.strip()
		directory = dfile.getAttribute('directory')
		shfile =  os.path.join(directory, filename)

		if (not os.path.exists(shfile)):
			fd = search_file(filename, self.gui_path_shader.val)
			if (fd):
				shfile = fd

		# nameid

		nid = ''
		el = root.getElementsByTagName('nameid')
		if (len(el) > 0):
			el[0].normalize()
			nid = el[0].firstChild.data.strip()

		# re-init object

		try:
			self.setup(shfile, nid)
		except:
			return False

		# shader's parameter

		for attr in root.getElementsByTagName('parameter'):
			name = attr.getAttribute('name')
			if (self.parameters.has_key(name)):
				attr.normalize()
				par = self.parameters[name]
				par.val = str(attr.firstChild.data.strip())

		return True

class Gelato_pyg(object):

	class name_mask(object):
		__slots__ = ['pyg', 'name', 'ext', 'suffix']

		def __init__(self, pyg, name = '', ext = '', suffix = False):
			self.pyg    = pyg
			self.name   = name
			self.ext    = ext
			self.suffix = suffix

		def __str__(self):
			l = [self.pyg.base, self.name]

			if (self.pyg.frame is None):
				l.extend([self.ext])
			else:
				n = self.pyg.mask % self.pyg.frame

				if (self.suffix and self.pyg.files_extensions):
					# file.ext.NNN
					l.extend([self.ext, n])
				else:
					# file.NNN.ext
					l.extend([n, self.ext])

			return ''.join(l)

	class data_st(object):
		__slots__ = ['s', 't']

		def __init__(self):
			self.s = []
			self.t = []

	class data_geometry(object):
		__slots__ = ['smooth', 'index_faces', 'nverts', 'verts', 'normals', 'uvlayers']

		def __init__(self):
			self.smooth      = False
			self.index_faces = []
			self.nverts      = []
			self.verts       = []
			self.normals     = []
			self.uvlayers    = {}

	class data_texture(object):
		__slots__ = ['name', 'filename', 'uvlayer', 'mapping', 'extend', 'texco', 'disp']

		def __init__(self, name, filename, uvlayer, mapping, extend, texco, disp = 0):
			self.name     = name
			self.filename = filename
			self.uvlayer  = uvlayer
			self.mapping  = mapping
			self.extend   = extend
			self.texco    = texco
			self.disp     = disp

	class data_mesh(object):
		__slots__ = ['db_geometry', 'points', 'nverts', 'verts', 'vertexcolors', 'uvname']

		def __init__(self, uvname):
			self.db_geometry  = {}
			self.points       = []
			self.nverts       = []
			self.verts        = []
			self.vertexcolors = []
			self.uvname       = uvname

	def __init__(self):
		"""
		Gelato class export.
		"""

		self.PRECISION     = 6
		self.PRECISION_FPS = 4
		self.EPSILON       = 1.E-7
		self.SCALEBIAS     = 0.1
		self.FACTORAMBIENT = 200

		self.EXT_SHADOWMAP = '.sm'
		self.EXT_TEXTURE   = '.tx'
		self.EXT_DIFFUSE   = '.sdb'
		self.EXT_PHOTONMAP = '.sdb'

		self.ZERO = ctypes.c_float(0.0)

		self.passes = EnumType('beauty', 'shadows', 'ambient_occlusion', 'photon_map', 'bake_diffuse')

		self.pbar = ProgressBar(78)

		# binary header

		if (sys.byteorder == 'little'):
			self.BINARY_INT   = 0200
			self.BINARY_FLOAT = 0202
		else:
			self.BINARY_INT   = 0201
			self.BINARY_FLOAT = 0203

		# FIXME
		self.convert_extend = dict([
			(Blender.Texture.ExtendModes.REPEAT,   'periodic'),
			(Blender.Texture.ExtendModes.CLIP,     'black'),
			(Blender.Texture.ExtendModes.CLIPCUBE, 'mirror'),
			(Blender.Texture.ExtendModes.EXTEND,   'clamp'),
#			(Blender.Texture.ExtendModes.CHECKER,  'periodic'),
		])

	def generate_instance_name(self, name, ext = '', prefix = '', postfix = '', noframe = False):

		slist = [prefix]

		slist.append(name)
		slist.append(postfix)

		if (self.instance is not None):
			slist.append('-')
			slist.append(str(self.instance))

		if (not (noframe or self.frame is None)):
			slist.append(str(self.mask % self.frame))

		slist.append(ext)

		return ''.join(slist)

	def generate_split_name(self, name, prefix, i, n, im, nm):

		slist = [self.base]

		if (self.npasses > 1):
			slist.append('_')
			slist.append(self.pass_name_file)

		slist.append('_')
		slist.append(prefix)
		slist.append('_')
		slist.append(name)

		if (n > 1):
			slist.append('-M')
			slist.append(str(i))

		if (nm > 1):
			slist.append('-B')
			slist.append(str(im))

		if (self.frame is not None):
			slist.append(str(self.mask % self.frame))

		slist.append(self.ext)

		return ''.join(slist)

	def object_name(self, name):
		if (self.instance is None):
			return name
		return self.generate_instance_name(name, prefix = '__', ext = '__', noframe = True)

	def camera_shadow_name(self, name):
		return self.generate_instance_name(name, prefix = '__shadow_', ext = '__', noframe = True)

	def camera_photon_map_name(self, name):
		return self.generate_instance_name(name, prefix = '__photon_map_', ext = '__', noframe = True)

	def file_shadow_name(self, name):
		return self.generate_instance_name(space2underscore(name), self.EXT_SHADOWMAP, self.base + '_shadow_')

	def file_diffuse_name(self, name):
		return self.generate_instance_name(space2underscore(name), self.EXT_DIFFUSE, self.base + '_diffuse_')

	def file_object_name(self, name, material_index, material_max, mbur_index, mbux_max):
		return self.generate_split_name(space2underscore(name), 'object', material_index, material_max, mbur_index, mbux_max)

	def file_output_pass(self):
		if (self.npasses <= 1):
			if (self.current_pass == self.passes.ambient_occlusion):
				return str(self.filename_ambient_occlusion)
			return str(self.filename)

		cpass= self.current_pass

		if (cpass == self.passes.beauty):
			return str(self.filename_beauty)
		elif (cpass == self.passes.shadows):
			return str(self.filename_shadows)
		elif (cpass == self.passes.ambient_occlusion):
			return str(self.filename_ambient_occlusion)
		elif (cpass == self.passes.photon_map):
			return str(self.filename_photon_map)
		elif (cpass == self.passes.bake_diffuse):
			return str(self.filename_bake_diffuse)

	def change_extension(self, filename, newext):
		if (self.enable_textures_tx):
			(base, ext) = os.path.splitext(filename)
			return base + newext

		return filename

	def construct_path(self, filename):
		if (self.enable_relative_paths):
			if (filename.startswith('//')):
				return filename[2:]
			return filename

		return Blender.sys.expandpath(filename)

	def write_matrix(self, matrix):
		"""
		Write 16 elements of matrix.
		"""

		self.file.write('(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n' % (
			matrix[0][0], matrix[0][1], matrix[0][2], matrix[0][3],
			matrix[1][0], matrix[1][1], matrix[1][2], matrix[1][3],
			matrix[2][0], matrix[2][1], matrix[2][2], matrix[2][3],
			matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]))

	def write_set_transform(self, matrix):
		"""
		Replace the current transformation
		"""

		self.file.write('SetTransform ')
		self.write_matrix(matrix)

	def write_append_transform(self, matrix):
		"""
		Concatenate the transformation
		"""

		self.file.write('AppendTransform ')
		self.write_matrix(matrix)

	def write_translation(self, matrix):
		"""
		Prepend a translation transformation
		"""

		trans  = matrix.translationPart()
		self.file.write('Translate (%s, %s, %s)\n' %
			(trans.x, trans.y, trans.z))

	def write_camera_transform(self, matrix):

#		m = Blender.Mathutils.Matrix(
#			[ 1.0,  0.0,   0.0, 0.0],
#			[ 0.0,  1.0,   0.0, 0.0],
#			[ 0.0,  0.0,  -1.0, 0.0],
#			[ 0.0,  0.0,   0.0, 1.0]) * matrix

		m = Blender.Mathutils.Matrix(
			[ matrix[0][0],  matrix[0][1],  matrix[0][2],  matrix[0][3]],
			[ matrix[1][0],  matrix[1][1],  matrix[1][2],  matrix[1][3]],
			[-matrix[2][0], -matrix[2][1], -matrix[2][2], -matrix[2][3]],
			[ matrix[3][0],  matrix[3][1],  matrix[3][2],  matrix[3][3]])

		if (self.verbose > 0):

			trans = m.translationPart()
#			scale = m.scalePart()
#			euler = m.toEuler()

			self.file.write('## Translate (%s, %s, %s)\n' %
				(trans.x, trans.y, trans.z))

#			self.file.write('## Scale (%s, %s, %s)\n' %
#				(scale.x, scale.y, scale.z))
#
#			self.file.write('## Rotate (%s, 1, 0, 0)\n' %
#				euler.x)
#
#			self.file.write('## Rotate (%s, 0, 1, 0)\n' %
#				euler.y)
#
#			self.file.write('## Rotate (%s, 0, 0, 1)\n' %
#				euler.z)

		self.write_set_transform(m)

	def write_move_scale_rotate(self, matrix):
		"""
		Calculate the move, scale and rotate matrix
		"""

		trans = matrix.translationPart()
		scale = matrix.scalePart()
		euler = matrix.toEuler()

		if ((abs(trans.x) >= self.EPSILON) or
			(abs(trans.y) >= self.EPSILON) or
			(abs(trans.z) >= self.EPSILON)):
				self.file.write('Translate (%s, %s, %s)\n' %
					(trans.x, trans.y, trans.z))

		self.file.write('Scale (%s, %s, %s)\n' %
			(scale.x, scale.y, -scale.z))

		if (abs(euler.z) >= self.EPSILON):
			self.file.write('Rotate (%s, 0, 0, 1)\n' % euler.z)

		if (abs(euler.y) >= self.EPSILON):
			self.file.write('Rotate (%s, 0, 1, 0)\n' % -euler.y)

		if (abs(euler.x) >= self.EPSILON):
			self.file.write('Rotate (%s, 1, 0, 0)\n' % -euler.x)

	def write_array(self, wfile, array, prefix = None, ascii = False):

		l = len(array)
		if (l == 0):
			return

		if (prefix):
			wfile.write(prefix)

		ty = type(array[0])

		if (self.enable_binary and not ascii):

			if (ty is int):

				wfile.write(ctypes.c_ubyte(self.BINARY_INT))
				wfile.write(ctypes.c_uint(l))

				for i in array:
					wfile.write(ctypes.c_uint(i))

			elif (ty is float):

				wfile.write(ctypes.c_ubyte(self.BINARY_FLOAT))
				wfile.write(ctypes.c_uint(l))

				for f in array:
					try:
						wfile.write(ctypes.c_float(f))
					except:
						wfile.write(self.ZERO)
		else:
			iarray = iter(array)

			if (ty is int):

				wfile.write('(%s' % iarray.next())

				for i in iarray:
					wfile.write(',%s' % i)

				wfile.write(')')

			elif (ty is float):

				wfile.write('(%s' % round(iarray.next(), self.PRECISION))

				for f in iarray:
					wfile.write(',%s' % round(f, self.PRECISION))

				wfile.write(')')

	def write_shadow_name(self, name = None, parameter = 'shadowname'):
		if (self.current_pass == self.passes.photon_map):
			return

		shadowname = None
		if (name and (self.shadow_maps or self.shadow_woo)):
			shadowname = self.file_shadow_name(name)
		elif (self.shadow_ray_traced):
			shadowname = 'shadows'

		if (shadowname):
			self.file.write('Parameter ("string %s", "%s")\n' %
				(parameter, shadowname))

	def write_ray_traced(self):
		self.file.write('Attribute ("int ray:maxdepth", %d)\n' %
			self.ray_traced_max_depth)

		if (self.shadow_ray_traced):
			self.file.write('Attribute ("float shadow:bias", %s)\n' %
				round(self.ray_traced_shadow_bias, self.PRECISION))

			self.file.write('Attribute ("int ray:opaqueshadows", %d)\n' %
				self.ray_traced_opaque_shadows)

			self.file.write('Attribute ("int ray:displace", %d)\n' %
				self.ray_displace)

			self.file.write('Attribute ("int ray:motion", %d)\n' %
				self.ray_motion)

		self.file.write('Attribute ("string geometryset", "+reflection")\n')
		self.file.write('Attribute ("string geometryset", "+refraction")\n')

	def write_shadow_ray_traced(self):
		self.file.write('\nAttribute ("string geometryset", "+shadows")\n')

	def write_key_fill_rim(self):
		self.file.write('\nInput ("cameralights.pyg")\n')

	def write_ambient_occlusion_pass1(self):
		if (not self.format):
			raise GelatoError, 'No output format'

		shader_ambient_occlusion = gelato_gui.assigned_material[0].get('ambient_occlusion')
		if (shader_ambient_occlusion is not None):
			self.file.write('\nAttribute ("string geometryset", "+%s")\n' %
				shader_ambient_occlusion['occlusionname'])

			self.file.write(str(shader_ambient_occlusion))
		else:
			self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
			self.file.write('Shader ("surface", "ambocclude", "string occlusionname", "localocclusion")\n')

	def write_ambient_occlusion_pass2(self):
		if (not self.format):
			raise GelatoError, 'No output format'

		output = str(self.output_ambient_occlusion_tx)

		self.file.write('\n')

		shader_environment_light = gelato_gui.assigned_light[0].get('environment_light')
		if (shader_environment_light is not None):
			shader_environment_light['occlusionmap'] = output

			shader_ambient_occlusion = gelato_gui.assigned_material[0].get('ambient_occlusion')
			if (shader_ambient_occlusion is not None):
				shader_environment_light['occlusionname'] = shader_ambient_occlusion['occlusionname']

			self.file.write(str(shader_environment_light))
		else:
			self.file.write('Light ("__envlight_pass2__", "envlight", "string occlusionmap", "%s" )\n' %
				output)

	def write_shader_photon_map_pass1(self):

		self.file.write('\nPushAttributes ()\n')

		shader_shoot_photons = gelato_gui.assigned_material[0].get('shoot_photons')
		if (shader_shoot_photons is not None):

			shader_shoot_photons['envname'] = 'reflection'

			self.file.write(str(shader_shoot_photons))
		else:
			self.file.write('Shader ("surface", "shootphotons", "string envname", "reflection")\n')

		self.file.write('Input ("frontplane.pyg")\n')

		self.file.write('PopAttributes ()\n')

		self.file.write('\nAttribute ("string geometryset", "+shadows")\n')
		self.file.write('Attribute ("string geometryset", "+reflection")\n')
		self.file.write('Attribute ("string user:caustic_photonfile", "%s")\n' %
			str(self.output_photon_map))

		self.file.write('\nShader ("surface", "defaultsurface")\n')

	def write_shader_photon_map_pass2(self):

		self.file.write('\n')

		shader_caustic_light = gelato_gui.assigned_light[0].get('caustic_light')
		if (shader_caustic_light is not None):

			shader_caustic_light['photonfile'] = str(self.output_photon_map)

			self.file.write(str(shader_caustic_light))

		else:
			self.file.write('Light ("__causticlight__", "causticlight",'
					'"string photonfile", "%s")\n' %
				str(self.output_photon_map))

		self.file.write('\nAttribute ("string geometryset", "+shadows")\n')
		self.file.write('Attribute ("string geometryset", "+reflection")\n')

	def write_indirect_light(self):

		if (self.verbose > 0):
			self.file.write('\n## Indirect light\n\n')

		self.file.write('Attribute ("string geometryset", "+indirect")\n')
		self.file.write('Attribute ("int indirect:minsamples", %d)\n' %
			self.indirect_minsamples)

		self.file.write('\n')

		shader_indirect_light = gelato_gui.assigned_light[0].get('indirect_light')
		if (shader_indirect_light is not None):
			self.file.write(str(shader_indirect_light))
		else:
			self.file.write('Light ("__indirectlight__", "indirectlight")\n')

	def write_background_color(self):
		if (not self.world):
			return

		# the horizon color
		col = self.world.hor

		self.file.write('\nPushAttributes ()\n')

		self.file.write('Attribute ("color C", (%s, %s, %s))\n' % (
			round(col[0], self.PRECISION),
			round(col[1], self.PRECISION),
			round(col[2], self.PRECISION)))

		self.file.write('Shader ("surface", "constant")\n')
		self.file.write('Input ("backplane.pyg")\n')

		self.file.write('PopAttributes ()\n')

	def write_ambientlight(self):
		if (not self.world):
			return

		# the ambient color
		col = self.world.amb

		if (col != [0.0, 0.0, 0.0]):
			self.file.write('\nLight ("%s", "ambientlight", '
					'"float intensity", %s, '
					'"color lightcolor", (%s, %s, %s))\n' % (
				self.world.name,
				self.lights_factor / self.FACTORAMBIENT,
				round(col[0], self.PRECISION),
				round(col[1], self.PRECISION),
				round(col[2], self.PRECISION)))

	@staticmethod
	def nonspecular(lamp):
		if (lamp.mode & Blender.Lamp.Modes.NoSpecular):
			return 1.0
		return 0.0

	def write_pointlight(self, obj, lamp, matrix):
		name = obj.name

		self.write_translation(matrix)
		self.write_shadow_name(name)

		self.file.write('Light ("%s", "pointlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float __nonspecular", %s)\n' % (
			self.object_name(name),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			self.nonspecular(lamp)))

	def write_distantlight(self, obj, lamp, matrix):
		name = obj.name

		self.write_move_scale_rotate(matrix)
		self.write_shadow_name(name)

		self.file.write('Light ("%s", "distantlight", '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float shadowsamples", %s, '
				'"float shadowbias", %s, '
				'"float __nonspecular", %s)\n' % (
			self.object_name(name),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			float(lamp.samples),
			lamp.bias * self.SCALEBIAS,
			self.nonspecular(lamp)))

	def write_spotlight(self, obj, lamp, matrix):
		name = obj.name

		self.write_move_scale_rotate(matrix)
		self.write_shadow_name(name)

		self.file.write('Light ("%s", "spotlight", '
				'"float falloff", 2.0, '
				'"float intensity", %s, '
				'"color lightcolor", (%s, %s, %s), '
				'"float coneangle", %s, '
				'"float conedeltaangle", %s, '
				'"float shadowsamples", %s, '
				'"float shadowbias", %s, '
				'"float __nonspecular", %s)\n' % (
			self.object_name(name),
			lamp.getEnergy() * self.lights_factor,
			lamp.R, lamp.G, lamp.B,
			math.radians(lamp.spotSize / 2.0),
			math.radians(lamp.spotBlend * lamp.spotSize / 4.0),
			float(lamp.samples),
			lamp.bias * self.SCALEBIAS,
			self.nonspecular(lamp)))

	def write_device(self, output_name, driver, data, camera_name):
		self.file.write('\n')

		if (driver != 'null'):

			self.file.write('Parameter ("string filter", "%s")\n' %
				self.filter)

			self.file.write('Parameter ("float[2] filterwidth", (%s, %s))\n' % (
				round(self.filterwidth_x, self.PRECISION),
				round(self.filterwidth_y, self.PRECISION)))

			self.file.write('Parameter ("float gain", %s)\n' %
				round(self.gain, self.PRECISION))

			self.file.write('Parameter ("float gamma", %s)\n' %
				round(self.gamma, self.PRECISION))

			if ((driver != 'iv') and self.compression):
				self.file.write('Parameter ("string compression", "%s")\n' %
					self.compression)

			if (driver != 'OpenEXR'):
				self.file.write('Parameter ("float dither", %s)\n' %
					self.dither)

				self.file.write('Parameter ("int[4] quantize", (%s, %s, %s, %s))\n' % (
					int(self.quantize_zero),
					int(self.quantize_one),
					int(self.quantize_min),
					int(self.quantize_max)))
			else:
				self.file.write('Parameter ("string software", "Blender Gelato %s")\n' %
					__version__)

			if (driver == 'iv'):
				self.file.write('Parameter ("int remote", 1)\n')

			if (self.enable_stereo and (self.current_pass == self.passes.beauty)):
				(base, ext) = os.path.splitext(output_name)

				if (self.files_extensions):
					(base, ext2) = os.path.splitext(base)
					ext = ext2 + ext

				self.file.write('Parameter ("string stereo:left", "%s")\n' %
					(base + '-left' + ext))

				self.file.write('Parameter ("string stereo:right", "%s")\n' %
					(base + '-right' + ext))

		self.file.write('Output ("%s", "%s", "%s", "%s")\n' %
			(output_name, driver, data, camera_name))

	def write_camera(self, obj):
		if (obj.type != 'Camera'):
			return

		name	= obj.name
		matrix	= obj.getMatrix()
		cam	= Blender.Camera.Get(obj.data.name)

		aspec_x = self.context.aspectX
		aspec_y = self.context.aspectY

		ratio   = self.sizex / self.sizey
		i_ratio = self.sizey / self.sizex

		fraction   = aspec_x / aspec_y
		i_fraction = aspec_y / aspec_x

		scale = cam.scale

		self.file.write('\nPushTransform ()\n')
		self.file.write('PushAttributes ()\n')

		# transform

		self.write_camera_transform(matrix)

		# clipping planes

		self.file.write('Attribute ("float near", %s)\n' %
			round(cam.clipStart, self.PRECISION))

		self.file.write('Attribute ("float far", %s)\n' %
			round(cam.clipEnd, self.PRECISION))

		# perspective camera

		ty = cam.type

		if (ty == 'persp'):

			fac = (i_ratio if (self.sizex > self.sizey) else fraction)

			if (aspec_x != aspec_y):

				height = 2.0

				aspx = ratio * height * 0.25
				aspy = i_fraction * height * 0.25

				self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
					(-aspx, aspx, -aspy, aspy))

				fac *= 4.0 / height

			fov = 2.0 * math.degrees(math.atan2(16.0 * fac, cam.lens))

			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %s)\n' %
				round(fov, self.PRECISION))

		# orthographic camera

		elif (ty == 'ortho'):

			aspx = scale / 2.0
			aspy = aspx * i_ratio * i_fraction

			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
				(-aspx, aspx, -aspy, aspy))

		else:
			raise GelatoError, 'Invalid camera type "%s"' % cam.type

		self.file.write('Attribute ("float pixelaspect", %s)\n' % fraction)

		# depth of field

		if (self.enable_dof and (self.current_pass == self.passes.beauty)):

			self.file.write('Attribute ("int dofquality", %d)\n' %
				self.dofquality)

			if (self.fstop):
				self.file.write('Attribute ("float fstop", %s)\n' %
					float(self.fstop))

			if (self.focallength):
				self.file.write('Attribute ("float focallength", %s)\n' %
					float(self.focallength))

			self.file.write('Attribute ("float focaldistance", %s)\n' %
				cam.dofDist)

		# motion blur

		if (self.enable_motion_blur and (self.current_pass in [self.passes.beauty, self.passes.ambient_occlusion])):

			self.file.write('Attribute ("int temporalquality", %s)\n' %
				self.temporal_quality)

			self.file.write('Attribute ("float[2] shutter", (%s, %s))\n' %
				(self.shutter_open, self.shutter_close))

		# stereo camera

		if (self.enable_stereo and (self.current_pass == self.passes.beauty)):

			self.file.write('Attribute ("float stereo:separation", %s)\n' %
				float(self.stereo_separation))

			self.file.write('Attribute ("float stereo:convergence", %s)\n' %
				float(self.stereo_convergence))

			self.file.write('Attribute ("string stereo:projection", "%s")\n' %
				self.stereo_projection)

			self.file.write('Attribute ("string stereo:shade", "%s")\n' %
				self.stereo_shade)

		# camera

		self.file.write('Camera ("%s")\n' % name)

		self.file.write('PopAttributes ()\n')
		self.file.write('PopTransform ()\n')

	def write_camera_light(self, obj, lamp, name, matrix):
		self.file.write('\nPushTransform ()\n')

		self.write_camera_transform(matrix)

		cname = self.camera_shadow_name(name)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "perspective", '
				'"float fov", %s, '
				'"float near", %s, '
				'"float far", %s)\n' % (
			cname,
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		if (self.enable_dynamic):
			self.file.write('Parameter ("int dynamic", 1)\n')

		shadow_data = ('avgz' if (self.shadow_woo) else 'z')

		self.file.write('Output ("%s", '
				'"shadow", "%s", "%s", '
				'"string compression", "%s", '
				'"string filter", "min", '
				'"float[2] filterwidth", (1.0, 1.0), '
				'"float dither", 0.0, '
				'"int[4] quantize", (0, 0, 0, 0))\n' % (
			self.file_shadow_name(name),
			shadow_data,
			cname,
			self.compression_shadow))

	def write_camera_photon_map(self, obj, lamp, name, matrix, projection = 'perspective'):
		self.file.write('\nPushTransform ()\n')

		self.write_camera_transform(matrix)

		cname = self.camera_photon_map_name(name)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "%s", '
				'"float fov", %s, '
				'"float near", %s, '
				'"float far", %s)\n' % (
			cname,
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			projection,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		self.file.write('Output ("%s", '
				'"null", '
				'"rgba", '
				'"%s")\n' % (
			self.title,
			cname))

	def write_motion(self, n):
		if (n < 2):
			return

		self.file.write('Motion ')
		self.write_array(self.file, range(n), '', True)
		self.file.write('\n')

	def write_script(self, name):
		if (not name):
			return

		try:
			txt = Blender.Text.Get(name)
		except:
			if (self.verbose > 1):
				print 'Error: invalid script "%s"' % name
			return

		if ((txt is None) or (txt.nlines < 1)):
			return

		self.file.write('## Script start: "%s"\n' % name)

		for line in txt.asLines():
			if (line):
				self.file.write(line)
				self.file.write('\n')

		self.file.write('## Script end: "%s"\n' % name)

	def generate_camera_shadows(self, obj, matrices):

		if (obj.type != 'Lamp'):
			return

		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		lname = lamp.name
		ltype = lamp.type

		if (len(matrices) == 1):
			mat = matrices[0]
		else:
			raise GelatoError, sys._getframe(0).f_code.co_name +' invalid number of items of input matrices'

		# check if shader light assign

		sd = gelato_gui.assigned_light[1].get(lname)
		if ((sd is not None) and (sd.widget_enable_shadow.val)):
			self.write_camera_light(obj, lamp, name, mat)
			return

		# only Spot, Sun, Lamp

		if (ltype in [Blender.Lamp.Types.Spot, Blender.Lamp.Types.Sun, Blender.Lamp.Types.Lamp]):
			self.write_camera_light(obj, lamp, name, mat)

	def generate_camera_photon_map(self, obj, matrices):
		if (obj.type != 'Lamp'):
			return

		photon_map = property_boolean_get(obj, 'photon_map')

		if (not photon_map):
			return

		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		lname = lamp.name
		ltype = lamp.type

		if (len(matrices) == 1):
			mat = matrices[0]
		else:
			raise GelatoError, sys._getframe(0).f_code.co_name +' invalid number of items of input matrices'

		if (ltype is Blender.Lamp.Types.Sun):
			self.write_camera_photon_map(obj, lamp, name, mat, 'orthographic')
		else:
			self.write_camera_photon_map(obj, lamp, name, mat)

	def generate_light(self, obj, matrices):

		if (obj.type != 'Lamp'):
			return

		name = obj.name
		lamp = Blender.Lamp.Get(obj.getData().name)

		lname = lamp.name
		ltype = lamp.type

		if (len(matrices) == 1):
			mat = matrices[0]
		else:
			raise GelatoError, sys._getframe(0).f_code.co_name + ' invalid number of items of input matrices'

		self.file.write('\nPushTransform ()\n')

		# prescript

		if (self.enable_scripts and property_boolean_get(obj, 'enable_prescript')):
			prescript = property_string_get(obj, 'prescript')
			if (prescript):
				self.write_script(prescript)

		# script

		if (self.enable_scripts and property_boolean_get(obj, 'enable_script')):

			script = property_string_get(obj, 'script')
			if (script):
				self.write_script(script)

		else:
			lsd = gelato_gui.assigned_light[1].get(lname)
			if (lsd is None):

				# automatic convection

				if (ltype is Blender.Lamp.Types.Lamp):
					self.write_pointlight(obj, lamp, mat)
				elif (ltype is Blender.Lamp.Types.Sun):
					self.write_distantlight(obj, lamp, mat)
				elif (ltype is Blender.Lamp.Types.Spot):
					self.write_spotlight(obj, lamp, mat)
				else:
					if (self.verbose > 1):
						print 'Info: excluded lamp "%s"' % name
			else:

				# shader light

				sd = copy.deepcopy(lsd)

				sd.nameid = self.object_name(name)

				self.write_move_scale_rotate(mat)

				# shadow

				if (sd.enable_shadow):
					self.write_shadow_name(name, sd.shadow)

				self.file.write(str(sd))

		# postscript

		if (self.enable_scripts and property_boolean_get(obj, 'enable_postscript')):
			postscript = property_string_get(obj, 'postscript')
			if (postscript):
				self.write_script(postscript)

		self.file.write('PopTransform ()\n')

	def write_geometry_head(self, obj, matrices):

		indirect_light = property_boolean_get(obj, 'indirect_light', True)

		self.file.write('\nPushAttributes ()\n')

		# prescript

		if (self.enable_scripts and property_boolean_get(obj, 'enable_prescript')):
			prescript = property_string_get(obj, 'prescript')
			if (prescript):
				self.write_script(prescript)

		self.file.write('Attribute ("string name", "%s")\n' %
			self.object_name(obj.name))

		if (not indirect_light):
			self.file.write('Attribute ("string geometryset", "-indirect")\n')

		self.write_motion(len(matrices))

		for m in matrices:
			self.write_set_transform(m)

	def write_geometry_tail(self, obj):

		# postscript

		if (self.enable_scripts and property_boolean_get(obj, 'enable_postscript')):
			postscript = property_string_get(obj, 'postscript')
			if (postscript):
				self.write_script(postscript)

		self.file.write('PopAttributes ()\n')

	def write_material_head(self, name, material, bake_diffuse):

		if (material is None):
			return

		mat_name = material.name
		flags    = material.mode

		# TODO remove >2.47
		enabled_textures = None
		try:
			enabled_textures = material.enabledTextures
		except:
			pass

		# texture files

		textures_color = []
		textures_displacement = []

		list_tex = material.getTextures()

		if (list_tex):
			for (idx, mtex) in enumerate(list_tex):

				if ((enabled_textures is not None) and (idx not in enabled_textures)):
					continue

				if ((not mtex) or (not mtex.tex)):
					continue

				if (mtex.tex.type is Blender.Texture.Types.IMAGE):
					image = mtex.tex.getImage()

					if ((not image) or (image.source is Blender.Image.Sources.GENERATED)):
						continue

					img_filename = image.getFilename()
					filename     = img_filename

					# Auto unpack image

					if (image.packed and self.enable_autounpack):

						if (not self.filetexture_memo.has_key(img_filename)):
							(base, ext) = os.path.splitext(img_filename)

							ftmp = tempfile.NamedTemporaryFile(suffix=ext, prefix='gelato')
							filename = ftmp.name
							ftmp.close()

							try:
								image.setFilename(filename)
								image.save()

							finally:
								image.setFilename(img_filename)

							self.filetexture_memo[img_filename] = filename

							if (self.verbose > 1):
								print 'Info: texture export "%s" -> "%s"' % (img_filename, ftmp.name)
						else:
							filename = self.filetexture_memo[img_filename]
					else:
						filename = self.construct_path(self.change_extension(img_filename, self.EXT_TEXTURE))

					# texture color

					if (mtex.mapto & Blender.Texture.MapTo.COL):
						textures_color.append(self.data_texture(mtex.tex.getName(),
							filename,
							mtex.uvlayer,
							mtex.mapping,
							mtex.tex.extend,
							mtex.texco))

					# texture displacement

					if (mtex.mapto & Blender.Texture.MapTo.DISP):
						textures_displacement.append(self.data_texture(mtex.tex.getName(),
							filename,
							mtex.uvlayer,
							mtex.mapping,
							mtex.tex.extend,
							mtex.texco,
							mtex.mtDisp * mtex.dispfac))

		self.file.write('PushAttributes ()\n')

		# prescript

		if (self.enable_scripts and property_boolean_get(material, 'enable_prescript')):
			prescript = property_string_get(material, 'prescript')
			if (prescript):
				self.write_script(prescript)

		if (self.current_pass not in [self.passes.ambient_occlusion, self.passes.shadows]):

			# script

			if (self.enable_scripts and property_boolean_get(material, 'enable_script')):
				script = property_string_get(material, 'script')
				if (script):
					self.write_script(script)
				return

			# color

			if (not (flags & Blender.Material.Modes.TEXFACE)):
				self.file.write('Attribute ("color C", (%s, %s, %s))\n' % (
					round(material.R, self.PRECISION),
					round(material.G, self.PRECISION),
					round(material.B, self.PRECISION)))

			# alpha

			alpha = material.alpha
			if (alpha < 1.0):
				alpha = round(alpha, self.PRECISION)
				self.file.write('Attribute ("color opacity", (%s, %s, %s))\n' %
					(alpha, alpha, alpha))

			# shadergroup

			enable_shadergroup = not self.enable_shader_debug and self.enable_textures and textures_color and (self.current_pass == self.passes.beauty)

			if (enable_shadergroup):
				self.file.write('ShaderGroupBegin ()\n')

			# texture color

			if ((not self.enable_shader_debug) and self.enable_textures):
				for ftex in textures_color:
					if (self.verbose > 0):
						self.file.write('## Texture color: "%s"\n' % ftex.name)

					self.file.write('Parameter ("string texturename", "%s")\n' % fix_file_name(ftex.filename))
					self.file.write('Parameter ("string wrap", "%s")\n' % self.convert_extend[ftex.extend])
					self.file.write('Shader ("surface", "pretexture")\n')

			# shader surface

			if ((not self.enable_shader_debug) and (self.verbose > 0)):
				self.file.write('## Material: "%s"\n' % mat_name)

			if (self.enable_shaders and not (self.enable_shader_debug or (self.current_pass == self.passes.photon_map))):

				if ((not (flags & Blender.Material.Modes.SHADELESS)) and not (bake_diffuse and (self.current_pass == self.passes.bake_diffuse))):

					sd = gelato_gui.assigned_material[1].get(mat_name)
					if (sd is None):
						# default plastic
						self.file.write('Shader ("surface", "plastic")\n')
					else:
						if (bake_diffuse and self.enable_bake_diffuse and sd.enable_sss and (self.current_pass == self.passes.beauty)):
							nsd = copy.deepcopy(sd)
							nsd[sd.sss] = self.file_diffuse_name(name)
							sd = nsd

						self.file.write(str(sd))

			if (enable_shadergroup):
				self.file.write('ShaderGroupEnd ()\n')

		# texture displacement

		if (self.enable_displacements):

			esg = len(textures_displacement) > 1

			if (esg):
				self.file.write('ShaderGroupBegin ()\n')

			for ftex in textures_displacement:
				if (self.verbose > 0):
					self.file.write('## Texture displacement: "%s"\n' % ftex.name)

				self.file.write('Parameter ("string texturename", "%s")\n' % fix_file_name(ftex.filename))
				self.file.write('Parameter ("string wrap", "%s")\n' % self.convert_extend[ftex.extend])
				self.file.write('Parameter ("float Km", %s)\n' %  round(ftex.disp, self.PRECISION))
				self.file.write('Shader ("displacement", "dispmap")\n')

			if (esg):
				self.file.write('ShaderGroupEnd ()\n')

		# photon map

		if ((self.current_pass == self.passes.photon_map) and (self.current_pass not in [self.passes.ambient_occlusion, self.passes.shadows])):

			raytransp = (flags & Blender.Material.Modes.RAYTRANSP) != 0
			raymirror = (flags & Blender.Material.Modes.RAYMIRROR) != 0

			if (raytransp):
				self.file.write('Parameter ("float eta", %s)\n' %
					material.IOR)

				self.file.write('Parameter ("float Kt", %s)\n' %
					material.specTransp)

			if (raymirror):
				self.file.write('Parameter ("float Kr", %s)\n' %
					material.rayMirr)

			if (raytransp or raymirror):
				self.file.write('Parameter ("float Kd", %s)\n' %
					material.diffuseSize)

				self.file.write('Parameter ("float Ks", %s)\n' %
					material.specSize)

				self.file.write('Parameter ("float roughness", %s)\n' %
					material.roughness)

				self.file.write('Parameter ("color specularcolor", (%s, %s, %s))\n' % (
					round(material.specR, self.PRECISION),
					round(material.specG, self.PRECISION),
					round(material.specB, self.PRECISION)))

				self.file.write('Parameter ("color transmitcolor", (%s, %s, %s))\n' % (
					round(material.mirR, self.PRECISION),
					round(material.mirG, self.PRECISION),
					round(material.mirB, self.PRECISION)))

			self.file.write('Parameter ("string envname", "reflection")\n')
			self.file.write('Shader ("surface", "movephotons")\n')


		# FIXME MA_ONLYCAST ???
		if (flags & 0x2000):
			self.file.write('Attribute ("string geometryset", "-camera")\n')

		if (not (flags & Blender.Material.Modes.TRACEABLE)):
			self.file.write('Attribute ("string geometryset", "-shadows")\n')

		if (flags & Blender.Material.Modes.TRANSPSHADOW):
			self.file.write('Attribute ("int ray:opaqueshadows", 0)\n')

	def write_material_tail(self, material):
		if (material is None):
			return

		self.file.write('PopAttributes ()\n')

	def write_material_postscript(self, material):
		if (material is None):
			return

		# postscript

		if (self.enable_scripts and property_boolean_get(material, 'enable_postscript')):
			postscript = property_string_get(material, 'postscript')
			if (postscript):
				self.write_script(postscript)

	def process_obj_transformation(self, obj, mblur, dup = False):

		motionblur_transformation = property_boolean_get(obj, 'motionblur_transformation', True)

		if (not ((self.current_pass in [self.passes.beauty, self.passes.ambient_occlusion]) and (mblur and motionblur_transformation))):

			return [obj.matrix]

		else:
			# get current frame number

			curframe = Blender.Get('curframe')

			try:
				matrixs = []

				for i in xrange(self.frames_transformation - 1, -1, -1):

					f = curframe - i
					if (f < 1):
						f = 1

					Blender.Set('curframe', f)

					if (dup):
						dup_matrixs = []
						for dobj, mat in obj.DupObjects:
							dup_matrixs.append(mat.copy())

						matrixs.append(dup_matrixs)
					else:
						matrixs.append(obj.matrix.copy())

				return matrixs

			finally:
				# restore frame number

				Blender.Set('curframe', curframe)

	def process_mesh_deformation(self, obj):

		# motion blur deformation

		motionblur_deformation = property_boolean_get(obj, 'motionblur_deformation')

		if  (not ((self.current_pass in [self.passes.beauty, self.passes.ambient_occlusion]) and  self.enable_motion_blur and  motionblur_deformation)):

			mesh = Blender.Mesh.New()
			mesh.getFromObject(obj, 0, 1)

			return [mesh]
		else:
			# get current frame number

			curframe = Blender.Get('curframe')

			try:
				meshes = []

				for i in xrange(self.frames_deformation - 1, -1, -1):

					f = curframe - i
					if (f < 1):
						f = 1

					Blender.Set('curframe', f)

					mesh = Blender.Mesh.New()
					mesh.getFromObject(obj, 0, 1)

					meshes.append(mesh)

				return meshes

			finally:
				# restore frame number

				Blender.Set('curframe', curframe)

	def generate_mesh(self, obj, matrices):

		if (obj.type not in ['Mesh', 'Surf']):
			return

		name = obj.name

		# get meshes

		try:
			meshes = self.process_mesh_deformation(obj)
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())
			return

		nmeshes = len(meshes)
		if (nmeshes < 1):
			return

		nfaces = len(meshes[0].faces)
		if (nfaces < 1):
			return

		# get properties

		catmull_clark = property_boolean_get(obj, 'catmull_clark')
		raster_width  = property_boolean_get(obj, 'raster_width')
		bake_diffuse  = property_boolean_get(obj, 'bake_diffuse')
		enable_proxy  = property_boolean_get(obj, 'enable_proxy')

		# interpolation type

		interpolation = ('catmull-clark' if (catmull_clark) else 'linear')

		# single sided face

		single_sided = not (self.enable_double_sided or (meshes[0].mode & Blender.Mesh.Modes.TWOSIDED))

		# if NURBS smooth surfaces

		all_smooth = (obj.type == 'Surf')

		# vertex color

		vtcolor = meshes[0].vertexColors

		# UV map

		faceuv = (self.enable_uv and meshes[0].faceUV)

		# loop meshes

		db_mesh = []

		for mesh in meshes:

			if (vtcolor):
				nlist_col = range(len(mesh.verts))

			# new mesh

			dmesh = self.data_mesh(mesh.renderUVLayer)
			db_mesh.append(dmesh)

			db_geometry = dmesh.db_geometry

			# loop faces

			for index_face, face in enumerate(mesh.faces):

				fsmooth = face.smooth
				nverts  = len(face.verts)

				# new geometry

				dgeometry = db_geometry.setdefault(face.mat, self.data_geometry())

				if (fsmooth):
					dgeometry.smooth = True

				dgeometry.index_faces.append(index_face)

				if (catmull_clark):
					dmesh.nverts.append(nverts)
				else:
					dgeometry.nverts.append(nverts)

				# loop vertexes

				if (catmull_clark):

					for v in face.verts:

						# vertexes index

						dmesh.verts.append(v.index)
				else:

					for v in face.verts:

						# vertexes index

						dgeometry.verts.append(v.index)

						# normals

						no = (v.no if (all_smooth or fsmooth) else face.no)

						dgeometry.normals.extend([no[0], no[1], no[2]])

				if (vtcolor):
					for j in xrange(len(face.verts)):
						c = face.col[j]
						nlist_col[face.verts[j].index] = [c.r, c.g, c.b]

			# loop vertexes

			for v in mesh.verts:

				# points

				dmesh.points.extend([v.co.x, v.co.y, v.co.z])

			# vertex color

			if (vtcolor):
				for c in nlist_col:
					try:
						dmesh.vertexcolors.extend([c[0]/255.0, c[1]/255.0, c[2]/255.0])
					except:
						dmesh.vertexcolors.extend([0.0, 0.0, 0.0])

			# UV layers

			if (faceuv):

				# save UV layer name

				actlname = mesh.activeUVLayer

				try:
					(ua, ub) = ((1.0, -1.0) if self.flip_u else (0.0, 1.0))
					(va, vb) = ((1.0, -1.0) if self.flip_v else (0.0, 1.0))

					for lname in mesh.getUVLayerNames():

						# select UV layer name

						mesh.activeUVLayer = lname

						for face in mesh.faces:

							uvlayers = dmesh.db_geometry[face.mat].uvlayers

							st = uvlayers.setdefault(lname, self.data_st())

							for uv in face.uv:
								st.s.append(round(ua + ub * uv[0], self.PRECISION))
								st.t.append(round(va + vb * uv[1], self.PRECISION))

				finally:
					# restore UV layer name

					mesh.activeUVLayer = actlname

		nmesh = len(db_mesh)

		if (nmesh != nmeshes):
			raise GelatoError, sys._getframe(0).f_code.co_name + ' invalid number of items'

		self.write_geometry_head(obj, matrices)

		# bake diffuse

		if (bake_diffuse and (self.current_pass == self.passes.bake_diffuse)):

			self.file.write('Attribute ("int cull:occlusion", 0)\n')
			self.file.write('Attribute ("int dice:rasterorient", 0)\n')

			shader_bake_diffuse = gelato_gui.assigned_material[0].get('bake_diffuse')
			file_name = self.file_diffuse_name(name)

			if (shader_bake_diffuse is not None):

				sd = copy.deepcopy(shader_bake_diffuse)
				sd['filename'] = file_name
				self.file.write(str(sd))
			else:
				self.file.write('Shader ("surface", "bakediffuse", '
						'"string filename", "%s", '
						'"float weightarea", 1, '
						'"float interpolate", 1)\n' %
							file_name)

		# proxy

		if (enable_proxy):

			proxy_file = property_string_get(obj, 'proxy_file')

			if (proxy_file):

				materials = obj.getMaterials()

				mat = None

				if ((len(materials) > 0) and (self.current_pass not in [self.passes.ambient_occlusion, self.passes.shadows])):
					mat = materials[0]
					self.write_material_head(name, mat, bake_diffuse)

				self.write_material_postscript(mat)

				self.file.write('Input ("%s")\n' % fix_file_name(self.construct_path(proxy_file)))

				if (mat):
					self.write_material_tail(mat)

		else:
			# materials

			multiple_mat = len(meshes[0].materials) > 1
			if (multiple_mat and catmull_clark):
				set_mat = set(range(nfaces))

			halo = False
			flags = 0
			ngeometry = len(db_mesh[0].db_geometry)

			for mat_index, dgeometry in db_mesh[0].db_geometry.iteritems():

				mat = None

				try:
					if (obj.colbits & (1 << mat_index)):
						# object's material
						mat = obj.getMaterials()[mat_index]
					else:
						# mesh's material
						mat = meshes[0].materials[mat_index]
				except:
					if (self.verbose > 1):
						sys.excepthook(*sys.exc_info())

				if (mat is not None):
					flags = mat.mode
					halo = (self.enable_halos and (flags & Blender.Material.Modes.HALO))

				# material

				self.write_material_head(name, mat, bake_diffuse)

				# material script

				self.write_material_postscript(mat)

				# multiple materials on a single mesh

				if (multiple_mat and catmull_clark):
					holes = list(set_mat - set(dgeometry.index_faces))
				else:
					holes = []

				# nverts and verts

				if (catmull_clark):
					nverts = dmesh.nverts
					verts  = dmesh.verts
				else:
					nverts = dgeometry.nverts
					verts  = dgeometry.verts

				# vertex color

				vertexcolors = dmesh.vertexcolors

				if (mat and (self.current_pass not in [self.passes.ambient_occlusion, self.passes.shadows])):

					if (not (self.enable_vextex_color and (flags & Blender.Material.Modes.VCOL_PAINT))):
						vertexcolors = []

				# motion blur

				if (self.current_pass != self.passes.shadows):
					self.write_motion(nmesh)

				# geometry

				for mesh_index, dmesh in enumerate(db_mesh):

					if (not self.enable_split):

						wfile = self.file
					else:

						fobj_name = self.file_object_name(name, mat_index, ngeometry, mesh_index, nmesh)

						self.file.write('Input ("%s")\n' % fobj_name)

						if (fobj_name not in self.fileobject_memo):

							wfile = open(fobj_name, 'wb')
							self.fileobject_memo.append(fobj_name)

							if (self.verbose > 1):
								print 'Info: exporting object file "%s"' % fobj_name
						else:
							continue

					points    = dmesh.points
					uvname    = dmesh.uvname
					dgeometry = dmesh.db_geometry[mat_index]

					uvlayers  = dgeometry.uvlayers

					npoint = len(points) / 3

					# normals

					normals = (dgeometry.normals if (all_smooth or dgeometry.smooth) else [])

					# write mesh

					if (single_sided):
						self.file.write('Attribute ("int twosided", 0)\n')

					if ((self.verbose > 0) and (not halo) and ((mesh_index < 1) or self.enable_split)):

						wfile.write('## Points: %s\n' % npoint)
						wfile.write('## Faces: %s\n' % len(nverts))

						if (self.enable_uvlayes):
							for lname in sorted(uvlayers):
								wfile.write('## UV: "%s"%s\n' % (lname, (' default' if (lname == uvname) else '')))

					if (halo):
						width = ('rasterwidth' if raster_width else 'width')

						wfile.write('Points (%s,"float %s",%s' %
							(npoint, width, mat.haloSize))

						self.write_array(wfile, points, ',"vertex point P",')
					else:
						wfile.write('Mesh ("%s"' % interpolation)

						self.write_array(wfile, nverts,       ',', True)
						self.write_array(wfile, verts,        ',', True)
						self.write_array(wfile, points,       ',"vertex point P",')
						self.write_array(wfile, normals,      ',"linear normal N",')
						self.write_array(wfile, vertexcolors, ',"vertex color C",')
						self.write_array(wfile, holes,        ',"int[%d] holes",' % len(holes), True)

						# UV

						if (uvlayers):
							for lname, st in uvlayers.iteritems():
								if (lname == uvname):
									s = 's'
									t = 't'
								else:
									if (not self.enable_uvlayes):
										continue

									s = 's_' + lname
									t = 't_' + lname

								self.write_array(wfile, st.s, ',"linear float %s",' % s)
								self.write_array(wfile, st.t, ',"linear float %s",' % t)

					wfile.write(')\n')

					if (self.enable_split):
						wfile.close()

				self.write_material_tail(mat)

		self.write_geometry_tail(obj)

	def visible(self, obj):
		"""
		Check if object is visible
		"""

		if ((obj.users > 1) and ((frozenset(obj.layers) & self.viewlayer) == frozenset())):
			if (self.verbose > 1):
				print 'Info: Object "%s" invisible' % obj.name
			return False
		return True

	def build(self, obj, fc, mblur = False):
		if ((not self.visible(obj)) or property_boolean_get(obj, 'excluded')):
			return

		self.instance = None

		if (self.enable_dupli_verts):
			try:
				# get duplicate object
				dupobjs = obj.DupObjects
			except:
				dupobjs = None

			if (dupobjs):

				self.instance = 0

				# check is motion blur
				if (mblur and (self.current_pass in [self.passes.beauty, self.passes.ambient_occlusion])):
					matrices = self.process_obj_transformation(obj, True, True)

					for dobj, m_dummy in dupobjs:

						new_matrices = []
						for m in matrices:
							new_matrices.append(m[self.instance])

						fc(dobj, new_matrices)
						self.instance += 1
				else:
					for dobj, mat in dupobjs:

						fc(dobj, [mat])
						self.instance += 1
				return
			else:
				try:
					# skip object if DupObjects
					if (obj.parent and obj.parent.DupObjects):
						return
				except:
					pass

		matrices = self.process_obj_transformation(obj, mblur)

		fc(obj, matrices)

	def lights_to_cameras(self):
		for obj in self.objects:
			self.build(obj, self.generate_camera_shadows)

	def lights_to_photon_maps(self):
		for obj in self.objects:
			self.build(obj, self.generate_camera_photon_map)

	def lights(self):
		n = len(self.objects)

		message = 'Lights ...'
		if (self.frame is not None):
			message += ' (%d/%d)' % (self.frame, self.nframes)

		self.pbar.setup(0, n - 1, message)

		if (self.current_pass != self.passes.photon_map):
			self.write_ambientlight()

		for i, obj in enumerate(self.objects):

			self.pbar(i)

			self.build(obj, self.generate_light)

		self.pbar.finish()

	def geometries(self):
		n = len(self.objects)

		message = 'Geometries ...'
		if (self.frame is not None):
			message += ' (%d/%d)' % (self.frame, self.nframes)

		self.pbar.setup(0, n - 1, message)

		for i, obj in enumerate(self.objects):

			self.pbar(i)

			if (self.verbose > 1):
				print 'Info: Object "%s" type "%s"' % (obj.name, obj.type)

			self.build(obj, self.generate_mesh, self.enable_motion_blur)

		self.pbar.finish()

	def write_head(self):
		"""
		Write pyg header.
		"""

		# get camera

		curcam = self.scene.objects.camera

		try:
			self.camera_name = curcam.name
		except:
			raise GelatoError, 'Camera is not present'

		scale = self.context.getRenderWinSize() / 100.0

		# banner

		self.file.write('## Exported by Blender Gelato %s\n##\n' % __version__)
		self.file.write(datetime.datetime.today().strftime('## Timestamp: %Y-%m-%d %H:%M:%S\n'))
		self.file.write('## Scene: %s\n' % self.scene.name)

		try:
			self.file.write('## User: %s\n' % getpass.getuser())
			self.file.write('## Hostname: %s\n' % socket.gethostname())
		except:
			pass

		self.file.write('## Blender: %s\n' % Blender.Get('version'))
		self.file.write('## Platform: %s\n' % sys.platform)
		self.file.write('## Pass: %s\n' % self.pass_name)

		if (self.frame is not None):
			self.file.write('## Frame: %d/%d\n' %
				(self.frame, self.nframes))

		self.file.write('\n')

		# header prescript

		if (self.enable_scripts and self.enable_header_prescript and self.header_prescript):
			self.write_script(self.header_prescript)

		# verbose

		self.file.write('Attribute ("int verbosity", %d)\n' %
			self.verbose)

		# error filename

		if (self.enable_error and self.error_filename):
			self.file.write('Attribute ("string error:filename", "%s")\n' %
				fix_file_name(self.error_filename))

		# threads

		if (not self.enable_auto_threads):
			self.file.write('Attribute ("int limits:threads", %d)\n' %
				self.limits_threads)

		# paths

		if (self.path_shader):
			self.file.write('Attribute ("string path:shader", "%s")\n' %
				fix_file_name(fix_vars(self.path_shader)))

		if (self.path_texture):
			self.file.write('Attribute ("string path:texture", "%s")\n' %
				fix_file_name(fix_vars(self.path_texture)))

		if (self.path_inputs):
			self.file.write('Attribute ("string path:input", "%s")\n' %
				fix_file_name(fix_vars(self.path_inputs)))

		if (self.path_imageio):
			self.file.write('Attribute ("string path:imageio", "%s")\n' %
				fix_file_name(fix_vars(self.path_imageio)))

		if (self.path_generator):
			self.file.write('Attribute ("string path:generator", "%s")\n' %
				fix_file_name(fix_vars(self.path_generator)))

		# resolution X and Y

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(self.sizex * scale), int(self.sizey * scale)))

		# border render

		if (self.context.borderRender):
			self.file.write('Attribute ("float[4] crop", (%s, %s, %s, %s))\n' % (
				self.context.border[0],
				self.context.border[2],
				1.0 - self.context.border[3],
				1.0 - self.context.border[1]))
		# antialiasing

		self.file.write('Attribute ("int[2] spatialquality", (%d, %d))\n' %
			(self.antialiasing_x , self.antialiasing_y))

		# rerender

		if (self.enable_rerender):
			self.file.write('Attribute ("int rerender", 1)\n')

			if (self.rerender_memory):
				self.file.write('Attribute ("int rerender:memory", %d)\n' %
					int(self.rerender_memory))

		# preview

		if (self.enable_preview):
			self.file.write('Attribute ("float preview", %s)\n' %
				round(self.preview_quality, self.PRECISION))

		# shading

		if (self.enable_shaders):
			self.file.write('Attribute ("float shadingquality", %s)\n' %
				round(self.shadingquality, self.PRECISION))

			self.file.write('Attribute ("int limits:gridsize", %s)\n' %
				self.limits_gridsize)

		#  bucket

		self.file.write('Attribute ("int[2] limits:bucketsize", (%d, %d))\n' %
			(self.bucketsize_x , self.bucketsize_y))

		self.file.write('Attribute ("string bucketorder", "%s")\n' %
			self.bucketorder)

		# mesh

		self.file.write('Attribute ("string orientation", "outside")\n')
		self.file.write('Attribute ("int twosided", 1)\n')

		# textures

		self.file.write('Attribute ("int texture:automipmap", %d)\n' %
			self.enable_automipmap)

		self.file.write('Attribute ("int limits:texturememory", %d)\n' %
			int(self.limits_texturememory))

		self.file.write('Attribute ("int limits:texturefiles", %d)\n' %
			int(self.limits_texturefiles))

		# displacement

		if (self.enable_displacements):
			self.file.write('Attribute ("float displace:maxradius", %s)\n' %
				float(self.maxradius))

			self.file.write('Attribute ("string displace:maxspace", "%s")\n' %
				self.maxspace)

		# units

		if (self.units_length):
			self.file.write('Attribute ("string units:length", "%s")\n' %
				self.units_length)

			self.file.write('Attribute ("float units:lengthscale", %s)\n' %
				round(float(self.units_lengthscale), self.PRECISION))

		# ray traced

		if (self.enable_ray_traced and (self.current_pass != self.passes.photon_map)):
			self.write_ray_traced()

		# photon map

		if (self.current_pass == self.passes.photon_map):
			self.file.write('Attribute ("int ray:maxdepth", %d)\n' %
				self.caustics_max_depth)

		# fps

		fps = float(self.context.fps) / self.context.fpsBase

		self.file.write('Attribute ("float units:fps", %s)\n' %
			round(fps, self.PRECISION_FPS))

		# motion blur

		if (self.enable_motion_blur):
			self.file.write('Attribute ("float units:timescale", 1.0)\n')
			self.file.write('Attribute ("string units:time", "frames")\n')
			self.file.write('Attribute ("float dice:motionfactor", %s)\n' %
				self.dice_motionfactor)

		# header postscript

		if (self.enable_scripts and self.enable_header_postscript and self.header_postscript):
			self.write_script(self.header_postscript)

		# camera/s

		if (self.current_pass != self.passes.photon_map):
			self.write_camera(curcam)

#			for obj in self.objects:
#				self.write_camera(obj)

		# shadows

		if ((self.shadow_maps or self.shadow_woo) and
			(((self.current_pass == self.passes.beauty) and self.enable_dynamic) or
			(self.current_pass == self.passes.shadows))):
				self.lights_to_cameras()

		# viewer

		if (self.enable_viewer and
			(self.current_pass in [self.passes.beauty, self.passes.ambient_occlusion, self.passes.bake_diffuse])):
				title = '%s - %s (%d/%d)' % (self.title, self.scene.name, self.curframe, self.nframes)
				self.write_device(title, 'iv', self.data_color, self.camera_name)

		# ambient occlusion

		if (self.current_pass == self.passes.ambient_occlusion):
			if (self.format):
				self.write_device(str(self.output_ambient_occlusion), self.format, self.data_color, self.camera_name)
			elif (self.npasses > 1):
				raise GelatoError, 'No output format'

		# photon map

		if (self.current_pass == self.passes.photon_map):
			self.lights_to_photon_maps()

		# output device

		if (self.format and (self.current_pass == self.passes.beauty)):
			self.write_device(str(self.output_color), self.format, self.data_color, self.camera_name)

			if (self.data_z):
				self.write_device(str(self.output_z), self.format, self.data_z, self.camera_name)

		if (self.current_pass == self.passes.shadows):
			self.write_device(self.title, 'null', self.data_color, self.camera_name)

		# photon map

		if (self.current_pass == self.passes.photon_map):
			self.file.write('\nAttribute ("string spatialdb:write", "%s")\n' %
				str(self.output_photon_map))

		if ((self.current_pass == self.passes.beauty) and self.pass_photon_maps):
			self.file.write('\nAttribute ("string spatialdb:read", "%s")\n' %
				str(self.output_photon_map))

		self.file.write('\nWorld ()\n')

		# world prescript

		if (self.enable_scripts and self.enable_world_prescript and self.world_prescript):
			self.file.write('\n')
			self.write_script(self.world_prescript)

	def write_tail(self):
		"""
		Write the final part of pyg file.
		"""

		# world postscript

		if (self.enable_scripts and self.enable_world_postscript and self.world_postscript):
			self.file.write('\n')
			self.write_script(self.world_postscript)

		self.file.write('\nRender ("%s")\n\n'
			% self.camera_name)

	def sequence(self, current_pass, pass_name):

		self.current_pass   = current_pass
		self.pass_name      = pass_name
		self.pass_name_file = space2underscore(self.pass_name.lower())

		# open file pyg

		fileout = self.file_output_pass()

		try:
			self.file = open(fileout, 'wb')

		except IOError:

			raise GelatoError, 'Cannot write file "%s"' % fileout
		except:
			sys.excepthook(*sys.exc_info())

		# write head of the file

		self.write_head()

		# ambient occlusion

		if (self.current_pass == self.passes.ambient_occlusion):
			self.write_ambient_occlusion_pass1()

		# background color

		if (self.enable_sky and (self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
			self.write_background_color()

		# ligths key fill rim

		if (self.enable_key_fill_rim and (self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
			self.write_key_fill_rim()

		# lights

		if (self.enable_lights and (self.current_pass in [self.passes.beauty, self.passes.photon_map, self.passes.bake_diffuse])):
			self.lights()

		# shadow ray traced

		if (self.shadow_ray_traced and (self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
			self.write_shadow_ray_traced()

		# only beauty

		if (self.current_pass == self.passes.beauty):

			# ambient occlusion

			if (self.enable_ambient_occlusion):
				self.write_ambient_occlusion_pass2()

			# indirect light

			if (self.enable_indirect_light):
				self.write_indirect_light()

			# caustics

			if (self.enable_caustics):
				self.write_shader_photon_map_pass2()

		# debug shader

		if (self.enable_shader_debug and (self.current_pass != self.passes.photon_map) and gelato_gui.shader_debug is not None):
			self.file.write('\n')
			self.file.write(str(gelato_gui.shader_debug))

		# photon map

		if (self.current_pass == self.passes.photon_map):
			self.write_shader_photon_map_pass1()

		# write all geometries

		self.geometries()

		# write tail of the file

		self.write_tail()

		# close file pyg

		self.file.close()

	def sequence_pass(self):

		# clear split file memo

		self.fileobject_memo = []

		# all passes

		if (self.pass_shadows):
			self.sequence(self.passes.shadows, 'Shadows')

		if (self.pass_ambient_occlusion):
			self.sequence(self.passes.ambient_occlusion, 'Ambient Occlusion')

		if (self.pass_photon_maps):
			self.sequence(self.passes.photon_map, 'Photon Map')

		if (self.pass_bake_diffuse):
			self.sequence(self.passes.bake_diffuse, 'Bake Diffuse')

		if (self.pass_beauty):
			self.sequence(self.passes.beauty, 'Beauty')

	def write_command(self):

		# shadows

		if (self.pass_shadows):
			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, self.filename_shadows))

		# photon maps

		if (self.pass_photon_maps):
			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, self.filename_photon_map))

		# ambient occlusion

		if (self.pass_ambient_occlusion):
			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, self.filename_ambient_occlusion))
			self.file.write('Command ("system", "string[4] argv", ("%s", "-o", "%s", "%s"))\n' %
				(MAKETX, self.output_ambient_occlusion_tx, self.output_ambient_occlusion))

		# diffuse

		if (self.pass_bake_diffuse):
			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, self.filename_bake_diffuse))

		# beauty

		if (self.pass_beauty):
			name = (self.filename if (self.npasses <= 1) else self.filename_beauty)

			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, name))

	def setup(self):

		# copy attributes

		for g in GUI_Base.registry(['config', 'local']):
			if g.name is None:
				continue
			setattr(self, g.name, g.val)

		# filename

		self.filename = fix_file_name(self.filename)

		# output data

		(self.data_color, self.data_z) = self.data

		# output file name image

		(self.format, self.suffix) = self.image_format[0:2]

		# image compression

		comp = self.image_format[2]
		self.compression = (None if (comp is None) else comp.val)

	def export(self, scene):

		# leave edit mode before getting the mesh

		editmode = Blender.Window.EditMode()
		if (editmode):
			Blender.Window.EditMode(0)

		Blender.Window.WaitCursor(1)

		# verbosity

		self.verbose = 1
		try:
			rt = Blender.Get('rt')
			if (rt == 42):
				self.verbose = 0
			elif (rt == 43):
				self.verbose = 2
		except:
			pass

		self.scene = scene

		# setup variable from GUI

		self.setup()

		# passes

		self.npasses = sum([self.pass_beauty, self.pass_shadows, self.pass_ambient_occlusion, self.pass_photon_maps, self.pass_bake_diffuse])
		if (self.npasses == 0):
			raise GelatoError, 'No pass select'

		self.staframe = Blender.Get('staframe')
		self.curframe = Blender.Get('curframe')
		self.endframe = Blender.Get('endframe')

		self.frame   = None
		self.nframes = self.endframe - self.staframe + 1

		self.mask = '.%%0%dd' % len('%d' % self.endframe)

		# file names, title and directoty

		(self.base, self.ext) = os.path.splitext(self.filename)
		(self.directory, file) = os.path.split(self.filename)
		self.title = os.path.basename(self.base)

		self.filename                    = self.name_mask(self, '',                   self.ext)
		self.filename_beauty             = self.name_mask(self, '_beauty',            self.ext)
		self.filename_shadows            = self.name_mask(self, '_shadows',           self.ext)
		self.filename_ambient_occlusion  = self.name_mask(self, '_ambient_occlusion', self.ext)
		self.filename_photon_map         = self.name_mask(self, '_photon_map',        self.ext)
		self.filename_bake_diffuse       = self.name_mask(self, '_bake_diffuse',      self.ext)

		self.output_ambient_occlusion_tx = self.name_mask(self, '_ambient_occlusion', self.EXT_TEXTURE,   True)
		self.output_photon_map           = self.name_mask(self, '_photon_map',        self.EXT_PHOTONMAP, True)

		if (self.suffix):
			self.output_color             = self.name_mask(self, '',                   self.suffix, True)
			self.output_z                 = self.name_mask(self, '_z',                 self.suffix, True)
			self.output_ambient_occlusion = self.name_mask(self, '_ambient_occlusion', self.suffix, True)

		if (self.verbose > 0):
			timestart = Blender.sys.time()
			print 'Info: starting Gelato pyg export to "%s"' % self.filename

		# set shader base

		Sbase.verbose = self.verbose

		# actives layer

		self.viewlayer = frozenset(Blender.Window.ViewLayers())

		self.objects = scene.objects

		self.world = Blender.World.GetCurrent()

		self.context = self.scene.getRenderingContext()
		self.sizex   = float(self.context.imageSizeX())
		self.sizey   = float(self.context.imageSizeY())

		self.filetexture_memo = {}

		try:
			if (self.enable_anim):

				if (not self.format):
					ret = Blender.Draw.PupMenu('Output null, continue ?%t|no%x1|yes%x2')
					if (ret != 2):
						return

				if (self.enable_viewer):
					ret = Blender.Draw.PupMenu('Window viewer enabled, continue ?%t|no%x1|yes%x2')
					if (ret != 2):
						return

				if (self.nframes <= 0):
					raise GelatoError, 'Invalid frame length'

				# all frames

				try:
					for self.frame in xrange(self.staframe, self.endframe + 1):
						Blender.Set('curframe', self.frame)

						if (self.verbose > 1):
							print 'Info: exporting frame %d' % self.frame

						self.sequence_pass()
				finally:
					Blender.Set('curframe', self.curframe)

			else:
				# single frame

				self.sequence_pass()

			# command file

			if ((self.frame is not None) or (self.npasses > 1) or self.pass_ambient_occlusion):

				self.frame = None

				try:
					self.file = open(str(self.filename), 'w')
				except IOError:
					raise GelatoError, 'Cannot write file "%s"' % self.filename

				if (self.enable_anim):
					for self.frame in xrange(self.staframe, self.endframe + 1):
						self.write_command()
				else:
					self.write_command()

				self.file.close()

		finally:
			self.pbar.finish()

		if (editmode):
			Blender.Window.EditMode(1)

		if (self.verbose > 0):
			print 'Info: finished Gelato pyg export (%.2fs)' % (Blender.sys.time() - timestart)


class GUI_Config(object):

	def __init__(self):
		self.active_obj = None
		self.active_mat = None

		self.shader_debug   = None
		self.shader_surface = None
		self.shader_light   = None

		self.list_shaders_debug   = []
		self.list_shaders_surface = []
		self.list_shaders_light   = []

		self.assigned_material     = [{}, {}]
		self.assigned_light        = [{}, {}]
		self.assigned_displacement = [{}, {}]	# TODO

		# widget color

		self.color_bg      = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.5325, 0.6936, 0.0])
		self.color_text    = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.0, 0.0, 0.0])
		self.color_evident = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [1.0, 1.0, 0.8])

		self.color_rect_sw = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.2, 0.2, 0.2])
		self.color_rect    = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.2392, 0.3098, 1.0])

		self.color_line    = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.4, 0.4, 0.4])

		# panels

		w = 100
		f = self.cb_panel

		self.panels = [

			[self.panel_output,            GUI_Toggle('local', 'panel_output',            'Output',         w, default = 1, func = f, help = 'Panel output data')],
			[self.panel_objects,           GUI_Toggle('local', 'panel_objects',           'Objects',        w, default = 0, func = f, help = 'Panel objects')],
			[self.panel_geometries,        GUI_Toggle('local', 'panel_geometries',        'Geometries',     w, default = 0, func = f, help = 'Panel geometries')],
			[self.panel_textures,          GUI_Toggle('local', 'panel_textures',          'Textures',       w, default = 0, func = f, help = 'Panel textures')],
			[self.panel_ray_traced,        GUI_Toggle('local', 'panel_ray_traced',        'Ray traced',     w, default = 0, func = f, help = 'Panel ray traced')],
			[self.panel_stereo,            GUI_Toggle('local', 'panel_stereo',            'Stereo',         w, default = 0, func = f, help = 'Panel stereo (anaglyph) rendering')],

			[self.panel_images,            GUI_Toggle('local', 'panel_images',            'Images',         w, default = 0, func = f, help = 'Panel images')],
			[self.panel_shaders,           GUI_Toggle('local', 'panel_shaders',           'Shaders',        w, default = 0, func = f, help = 'Panel shaders')],
			[self.panel_lights,            GUI_Toggle('local', 'panel_lights',            'Lights',         w, default = 0, func = f, help = 'Panel lights')],
			[self.panel_displacement,      GUI_Toggle('local', 'panel_displacement',      'Displacement',   w, default = 0, func = f, help = 'Panel displacement')],
			[self.panel_motion_blur,       GUI_Toggle('local', 'panel_motion_blur',       'Motion Blur',    w, default = 0, func = f, help = 'Panel Motion Blur')],
			[self.panel_depth_of_field,    GUI_Toggle('local', 'panel_depth_of_field',    'Depth of Field', w, default = 0, func = f, help = 'Panel depth of field')],

			[self.panel_shadows,           GUI_Toggle('local', 'panel_shadows',           'Shadows',        w, default = 0, func = f, help = 'Panel select shadows type')],
			[self.panel_ambient_occlusion, GUI_Toggle('local', 'panel_ambient_occlusion', 'AO',             w, default = 0, func = f, help = 'Panel ambient occlusion')],
			[self.panel_sss,               GUI_Toggle('local', 'panel_sss',               'SSS',            w, default = 0, func = f, help = 'Panel SubSurface Scattering')],
			[self.panel_caustics,          GUI_Toggle('local', 'panel_caustics',          'Caustics',       w, default = 0, func = f, help = 'Panel caustics')],
			[self.panel_indirect_light,    GUI_Toggle('local', 'panel_indirectlight',     'Indirect Light', w, default = 0, func = f, help = 'Panel indirect light')],
			[self.panel_environment,       GUI_Toggle('local', 'panel_environment',       'Environment',    w, default = 0, func = f, help = 'Panel environment')],

			[self.panel_pass,              GUI_Toggle('local', 'panel_pass',              'Pass',           w, default = 0, func = f, help = 'Panel select passes')],
			[self.panel_rerender,          GUI_Toggle('local', 'panel_rerender',          'Rerender',       w, default = 0, func = f, help = 'Panel select rerender')],
			[self.panel_scripts,           GUI_Toggle('local', 'panel_scripts',           'Scripts',        w, default = 0, func = f, help = 'Panel scripts')],
		]

		# panels init

		self.panel_common_init()

		for (f, pan) in self.panels:
			try:
				exec 'self.' + f.__name__ + '_init()'

			except:
				if (Sbase.verbose > 0):
					sys.excepthook(*sys.exc_info())

		# config filename

		base = ''
		try:
			(directory, filename) = os.path.split(self.gui_filename.val)
			(base, ext) = os.path.splitext(filename)
		except:
			pass

		if (not base):
			base = 'gelato'

		self.config_filename = base + '.xml'

		# avanable shaders

		self.assigned_material[0]['ambient_occlusion'] = None
		self.assigned_material[0]['shoot_photons']     = None
		self.assigned_material[0]['bake_diffuse']      = None

		self.assigned_light[0]['shoot_photons']  = None
		self.assigned_light[0]['indirect_light'] = None
		self.assigned_light[0]['caustic_light']  = None

		available_shaders = find_files('*.gso', self.gui_path_shader.val)
		if (available_shaders):

			for (filename, path) in sorted(available_shaders.iteritems()):
				fd = os.path.join(path, filename)
				try:
					sd = Shader(fd)

					ty = sd.type
					if (ty is None):
						continue

					(base, ext) = os.path.splitext(filename)

					# surface, generic

					if (ty in [Sbase.types.surface, Sbase.types.generic]):
						self.list_shaders_surface.append([base, sd])

						# shaders debug

						if (base in ['shownormals', 'showfacing', 'showst', 'showuv', 'showdudv', 'showgrids', 'raygoggles']):
							self.list_shaders_debug.append([base, copy.deepcopy(sd)])

						if (base == 'ambocclude'):

							ambocclude = copy.deepcopy(sd)

							ambocclude['occlusionname'] = 'localocclusion'

							self.assigned_material[0]['ambient_occlusion'] = ambocclude

						elif (base == 'shootphotons'):

							self.assigned_material[0]['shoot_photons'] = sd

						elif (base == 'bakediffuse'):

							self.assigned_material[0]['bake_diffuse'] = sd

					# light

					elif (ty is Sbase.types.light):
						self.list_shaders_light.append([base, sd])

						if (base == 'envlight'):

							envlight = copy.deepcopy(sd)

							envlight.nameid = '__envlight_pass2__'
							envlight['occlusionmap'] = '$FILE_PASS1'

							self.assigned_light[0]['shoot_photons'] = envlight

						elif (base == 'indirectlight'):

							indirectlight = copy.deepcopy(sd)

							indirectlight.nameid = '__indirectlight__'

							self.assigned_light[0]['indirect_light'] = indirectlight

						elif (base == 'causticlight'):

							causticlight = copy.deepcopy(sd)

							causticlight.nameid = '__causticlight__'

							self.assigned_light[0]['caustic_light'] = causticlight

				except:
					sys.excepthook(*sys.exc_info())
					print 'Error: shader "%s" not found disabled' % filename

		for data in [self.assigned_material[0], self.assigned_light[0]]:
			for k, d in data.iteritems():
				if (d is None):
					print 'Error: shader "%s.gso" not found disabled' % k

		GUI_Base.home()

	def draw(self):

		GUI_Base.home()

		Blender.BGL.glClearColor(self.color_bg[0], self.color_bg[1], self.color_bg[2], 1.0)
		Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)

		self.panel_common()

		GUI_Base.line_feed()

		self.panel_select()

	def handle_event(self, evt, val):

		# active object

		if (evt in [Blender.Draw.MOUSEX, Blender.Draw.MOUSEY]):
			obj = selected_object()
			if (obj):
				if (self.active_obj and (obj.name == self.active_obj.name)):
					return
				self.active_obj = obj
				Blender.Draw.Draw()

			elif (self.active_obj):
				self.active_obj = None
				Blender.Draw.Draw()

			return

		# only press

		if (not val):
			return

		if (evt in [Blender.Draw.ESCKEY, Blender.Draw.QKEY]):
			ret = Blender.Draw.PupMenu('OK?%t|Exit Blender Gelato%x1')
			if (ret == 1):
				self.config_save()
				Blender.Draw.Exit()
			return

		if (evt in [Blender.Draw.WHEELDOWNMOUSE, Blender.Draw.DOWNARROWKEY]):
			GUI_Base.home_down()
			Blender.Draw.Draw()
			return

		if (evt in [Blender.Draw.WHEELUPMOUSE, Blender.Draw.UPARROWKEY]):
			GUI_Base.home_up()
			Blender.Draw.Draw()
			return

		if (evt == Blender.Draw.HOMEKEY):
			GUI_Base.home_reset()
			Blender.Draw.Draw()
			return

		if (evt == Blender.Draw.LEFTARROWKEY):
			GUI_Base.home_left()
			Blender.Draw.Draw()
			return

		if (evt == Blender.Draw.RIGHTARROWKEY):
			GUI_Base.home_right()
			Blender.Draw.Draw()
			return

		if (evt == Blender.Draw.SKEY):
			self.cb_save(0, 0)
			return

		if (evt == Blender.Draw.RKEY):
			self.cb_render(0, 0)
			return

	def handle_button_event(self, evt):
		# pass

		if (self.gui_enable_dynamic.val or self.gui_shadow_ray_traced.val):
			self.gui_pass_shadows.val = 0

		if (not self.gui_enable_ambient_occlusion.val):
			self.gui_pass_ambient_occlusion.val = 0

		if (not self.gui_enable_caustics.val):
			self.gui_pass_photon_maps.val = 0

		if (not self.gui_enable_bake_diffuse.val):
			self.gui_pass_bake_diffuse.val = 0

		# passes

		if (self.gui_image_format.val[0] is None):
			self.gui_viewer.val = 1

		# config save

		self.config_save()

		Blender.Draw.Redraw(1)

	# callback panels

	def cb_panel(self, event, val):
		if (val):
			for func, pan in self.panels:
				if (pan.event != event):
					pan.val = 0
		else:
			self.panels[0][1].val = 1

	# callback panel common

	def cb_save(self, event, val):
		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

		except GelatoError, strerror:

			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_render(self, event, val):
		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

			# run gelato

			filename = self.gui_filename.val

			if (os.path.isfile(filename)):

				pid = subprocess.Popen([GELATO, filename]).pid

				print 'Info: run Gelato pid=%s' % pid

			else:
				raise GelatoError, 'No such file: `%s\'' % filename

		except GelatoError, strerror:

			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_default(self, event, val):
		ret = Blender.Draw.PupMenu('All items to default values ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		for group in GUI_Base.registry().itervalues():
			for data in group:
				data.setdefault()

		for data in [self.assigned_material[1:], self.assigned_light[1:]]:
			for shader in data:
				for sd in shader.itervalues():
					if (sd is not None):
						sd.setdefault()

	def cb_exit(self, event, val):
		self.handle_event(Blender.Draw.ESCKEY, 1)

	# callback filename

	def cb_select(self, name):
		self.gui_filename.val = os.path.abspath(name)

	def cb_filename(self, event, val):
		Blender.Window.FileSelector(self.cb_select, '.pyg', self.gui_filename.val)

	# callback error filename

	def cb_errorselect(self, name):
		self.gui_error_filename.val = os.path.abspath(name)

	def cb_error_filename(self, event, val):
		Blender.Window.FileSelector(self.cb_errorselect, '.txt', self.gui_error_filename.val)

	# callback pass

	def cb_pass(self, event, val):
		if ((not val) and (not (self.gui_pass_beauty.val or self.gui_pass_shadows.val or self.gui_pass_ambient_occlusion.val))):
			self.gui_pass_beauty.val = 1

	# callback shadows

	def cb_shadows(self, event, val):
		if (self.gui_shadow_maps.event != event):
			self.gui_shadow_maps.val = 0
		if (self.gui_shadow_woo.event != event):
			self.gui_shadow_woo.val = 0
		if (self.gui_shadow_ray_traced.event != event):
			self.gui_shadow_ray_traced.val = 0

	# callback properties

	def cb_delete_all_properties(self, event, val):
		ret = Blender.Draw.PupMenu('Are You Sure ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		for data in [Blender.Object.Get(), Blender.Material.Get()]:
			for obj in data:
				if (obj.properties.has_key('gelato')):
					del obj.properties['gelato']

	# callback objects

	def cb_obj_excluded(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'excluded', val)

	def cb_obj_enable_postscript(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_postscript', val)
			if (not val):
				property_set(obj, 'postscript', '')

	def cb_obj_enable_prescript(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_prescript', val)
			if (not val):
				property_set(obj, 'prescript', '')

	def cb_menu_obj_postscript(self, event, val):
		obj = self.active_obj
		script = self.gui_menu_obj_postscript.val
		if (obj and script):
			property_set(obj, 'postscript', script)

	def cb_menu_obj_prescript(self, event, val):
		obj = self.active_obj
		script = self.gui_menu_obj_prescript.val
		if (obj and script):
			property_set(obj, 'prescript', script)

	# callback geometries

	def cb_geo_catmull_clark(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'catmull_clark', val)

	def cb_geo_raster_width(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'raster_width', val)

	def cb_geo_bake_diffuse(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'bake_diffuse', val)

	def cb_geo_indirect_light(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'indirect_light', val)

	def cb_geo_mb_transformation(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'motionblur_transformation', val)

	def cb_geo_mb_deformation(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'motionblur_deformation', val)

	# callback proxy

	def cb_geo_enable_proxy(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_proxy', val)

	def cb_select_proxy(self, name):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'proxy_file', os.path.abspath(name))

	def cb_button_proxy_file(self, event, val):
		Blender.Window.FileSelector(self.cb_select_proxy, '.pyg', self.gui_proxy_file.val)

	def cb_proxy_file(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'proxy_file', val)

	# callback header script

	def cb_enable_header_postscript(self, event, val):
		if (not val):
			self.gui_header_postscript.setdefault()

	def cb_enable_header_prescript(self, event, val):
		if (not val):
			self.gui_header_prescript.setdefault()

	def cb_menu_header_postscript(self, event, val):
		script = self.gui_menu_header_postscript.val
		if (script):
			self.gui_header_postscript.val = script

	def cb_menu_header_prescript(self, event, val):
		script = self.gui_menu_header_prescript.val
		if (script):
			self.gui_header_prescript.val = script

	# callback world script

	def cb_enable_world_postscript(self, event, val):
		if (not val):
			self.gui_world_postscript.setdefault()

	def cb_enable_world_prescript(self, event, val):
		if (not val):
			self.gui_world_prescript.setdefault()

	def cb_menu_world_postscript(self, event, val):
		script = self.gui_menu_world_postscript.val
		if (script):
			self.gui_world_postscript.val = script

	def cb_menu_world_prescript(self, event, val):
		script = self.gui_menu_world_prescript.val
		if (script):
			self.gui_world_prescript.val = script

	# callback debug shaders

	def cb_enable_shader_debug(self, event, val):
		if (not val):
			self.shader_debug = None

	def cb_menu_shader_debug(self, event, val):
		sd = self.gui_menu_shader_debug.val
		if (sd is not None):
			# copy object no reference
			self.shader_debug = copy.deepcopy(sd)

	# callback materials

	def cb_button_mat_assign(self, event, val):
		material_name = self.gui_menu_material.val
		sd = self.gui_menu_shader.val
		if (material_name and sd):
			# copy object no reference
			self.assigned_material[1][material_name] = copy.deepcopy(sd)

	def cb_menu_shader(self, event, val):
		self.cb_button_mat_assign(0, 0)

	def cb_button_mat_remove(self, event, val):
		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		try:
			material_name = self.gui_menu_material.val
			del self.assigned_material[1][material_name]
		except:
			sys.excepthook(*sys.exc_info())

	def cb_mat_enable_postscript(self, event, val):
		mat = self.active_mat
		if (mat):
			property_set(mat, 'enable_postscript', val)
			if (not val):
				property_set(mat, 'postscript', '')

	def cb_mat_enable_script(self, event, val):
		mat = self.active_mat
		if (mat):
			property_set(mat, 'enable_script', val)
			if (not val):
				property_set(mat, 'script', '')

	def cb_mat_enable_prescript(self, event, val):
		mat = self.active_mat
		if (mat):
			property_set(mat, 'enable_prescript', val)
			if (not val):
				property_set(mat, 'prescript', '')

	def cb_menu_mat_postscript(self, event, val):
		mat = self.active_mat
		script = self.gui_menu_mat_postscript.val
		if (mat and script):
			property_set(mat, 'postscript', script)

	def cb_menu_mat_script(self, event, val):
		mat = self.active_mat
		script = self.gui_menu_mat_script.val
		if (mat and script):
			property_set(mat, 'script', script)

	def cb_menu_mat_prescript(self, event, val):
		mat = self.active_mat
		script = self.gui_menu_mat_prescript.val
		if (mat and script):
			property_set(mat, 'prescript', script)

	# callback light

	def cb_lamp_photon_map(self, event, val):
		obj = self.active_obj
		if (obj is not None):
			property_set(obj, 'photon_map', val)

	def cb_button_lamp_assign(self, event, val):
		lamp_name = self.gui_menu_lamp.val
		sd = self.gui_menu_light.val
		if (lamp_name and sd):
			# copy object no reference
			self.assigned_light[1][lamp_name] = copy.deepcopy(sd)

	def cb_gui_menu_light(self, event, val):
		self.cb_button_lamp_assign(0, 0)

	def cb_button_lamp_remove(self, event, val):
		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return
		try:
			lamp_name = self.gui_menu_lamp.val
			del self.assigned_light[1][lamp_name]
		except:
			sys.excepthook(*sys.exc_info())

	def cb_lamp_enable_postscript(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_postscript', val)
			if (not val):
				property_set(obj, 'postscript', '')

	def cb_lamp_enable_script(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_script', val)
			if (not val):
				property_set(obj, 'script', '')

	def cb_lamp_enable_prescript(self, event, val):
		obj = self.active_obj
		if (obj):
			property_set(obj, 'enable_prescript', val)
			if (not val):
				property_set(obj, 'prescript', '')

	def cb_menu_lamp_postscript(self, event, val):
		obj = self.active_obj
		script = self.gui_menu_lamp_postscript.val
		if (obj and script):
			property_set(obj, 'postscript', script)

	def cb_menu_lamp_script(self, event, val):
		obj = self.active_obj
		script = self.gui_menu_lamp_script.val
		if (obj and script):
			property_set(obj, 'script', script)

	def cb_menu_lamp_prescript(self, event, val):
		obj = self.active_obj
		script = self.gui_menu_lamp_prescript.val
		if (obj and script):
			property_set(obj, 'prescript', script)

	def draw_shader_help(self):

		GUI_Base.line_feed()

		GUI_Line.draw(self.color_line, 1, 0, 0, 650, False)

		GUI_Text.draw(Sbase.color_text, '${frame[:digit]} -> frame number', 0, 2, 10)

	def panel_select(self):

		func = None

		for idx, (f, pan) in enumerate(self.panels):

			pan.draw()

			if (pan.val == 1):
				func = f

			if ((idx != 19) and (idx % 6) == 5):
				GUI_Base.line_feed()

		GUI_Base.line_feed()

		GUI_Rect.draw(self.color_rect_sw, 2, 2, 650, 11, False)
		GUI_Rect.draw(self.color_rect,    0, 4, 650, 10)

		GUI_Base.line_feed()

		# call function's panel

		if (func):
			func()

	def panel_common_init(self):

		self.gui_save    = GUI_Button('local', None, 'Save',    70, func = self.cb_save,    help = 'Save pyg file')
		self.gui_render  = GUI_Button('local', None, 'Render',  80, func = self.cb_render,  help = 'Save and render pyg file')
		self.gui_default = GUI_Button('local', None, 'Default', 80, func = self.cb_default, help = 'Set all items to default values')
		self.gui_exit    = GUI_Button('local', None, 'Exit',    70, func = self.cb_exit,    help = 'Exit Python script')

	def panel_common(self):
		GUI_Text.draw(self.color_text, 'Blender Gelato V' + __version__, 130, 2, 6)

		self.gui_save.draw()
		self.gui_render.draw()

		GUI_Base.blank(170)

		self.gui_default.draw()
		self.gui_exit.draw()

	def panel_pass_init(self):

		w = 130
		f = self.cb_pass

		self.gui_pass_beauty            = GUI_Toggle('config', 'pass_beauty',            'Beauty',            w, default = 1, func = f, help = 'Enable beauty pass')
		self.gui_pass_shadows           = GUI_Toggle('config', 'pass_shadows',           'Shadows',           w, default = 0, func = f, help = 'Enable shadows pass')
		self.gui_pass_ambient_occlusion = GUI_Toggle('config', 'pass_ambient_occlusion', 'Ambient Occlusion', w, default = 0, func = f, help = 'Enable shadows pass')
		self.gui_pass_photon_maps       = GUI_Toggle('config', 'pass_photon_maps',       'Photon map',        w, default = 0, func = f, help = 'Enable photon map pass')
		self.gui_pass_bake_diffuse      = GUI_Toggle('config', 'pass_bake_diffuse',      'Bake diffuse',      w, default = 0, func = f, help = 'Enable bake diffuse pass')

	def panel_pass(self):

		self.gui_pass_beauty.draw()

		if ((not self.gui_enable_dynamic.val) and (self.gui_shadow_maps.val or self.gui_shadow_woo.val)):

			GUI_Base.line_feed(False)

			self.gui_pass_shadows.draw()

		if (self.gui_enable_ambient_occlusion.val):

			GUI_Base.line_feed(False)

			self.gui_pass_ambient_occlusion.draw()

		if (self.gui_enable_caustics.val):

			GUI_Base.line_feed(False)

			self.gui_pass_photon_maps.draw()

		if (self.gui_enable_bake_diffuse.val):

			GUI_Base.line_feed(False)

			self.gui_pass_bake_diffuse.draw()

	def panel_output_init(self):

		# file name

		base = ''
		try:
			blend_file_name = Blender.Get('filename')
			(base, ext) = os.path.splitext(blend_file_name)
			if (ext.lower() == '.gz'):
				(base, ext) = os.path.splitext(base)
		except:
			pass

		if (not base):
			base = 'gelato'

		filename = base + '.pyg'

		path_inputs    = ':'.join(['.', os.path.join('$GELATOHOME', 'inputs'),   '&'])
		path_texture   = ':'.join(['.', os.path.join('$GELATOHOME', 'textures'), '&'])
		path_shader    = ':'.join(['.', os.path.join('$GELATOHOME', 'shaders'),  '&'])
		path_imageio   = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])
		path_generator = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])

		self.gui_viewer         = GUI_Toggle('config', 'enable_viewer',         'Viewer',         100, default = 1, help = 'Enable window viewer')
		self.gui_split          = GUI_Toggle('config', 'enable_split',          'Split',          100, default = 0, help = 'Split out objects into separate files')
		self.gui_binary         = GUI_Toggle('config', 'enable_binary',         'Binary',         100, default = 0, help = 'Enable binary file')
		self.gui_relative_paths = GUI_Toggle('config', 'enable_relative_paths', 'Relative paths', 100, default = 1, help = 'Enable relative paths')
		self.gui_pack_config    = GUI_Toggle('blend',  'pack_config',           'Pack config',    100, default = 0, help = 'Enable pack config file (*.xml)')
		self.gui_auto           = GUI_Toggle('config', 'enable_auto_threads',   'Auto',           100, default = 1, help = 'Auto detect')
		self.gui_anim           = GUI_Toggle('config', 'enable_anim',           'Anim',           100, default = 0, help = 'Enable sequence render')
		self.gui_preview        = GUI_Toggle('config', 'enable_preview',        'Preview',        100, default = 0, help = 'Enable preview')
		self.gui_error          = GUI_Toggle('config', 'enable_error',          'Enable error',   100, default = 0, help = 'Enable error file')

		self.gui_button_error    = GUI_Button('local', None, 'Save:',     100, func = self.cb_error_filename, help = 'Select log file (default: ">>gelato_log.txt")', sep = 0)
		self.gui_button_filename = GUI_Button('local', None, 'Filename:', 100, func = self.cb_filename,       help = 'Select file name', sep = 0)

		self.gui_limits_threads = GUI_Number('config', 'limits_threads', 'Threads: ', 100, 1, 256,  default = 1,  help = 'Sets the maximum number of parallel execution threads')
		self.gui_bucketsize_x   = GUI_Number('config', 'bucketsize_x',   'X: ',       105, 1, 1000, default = 32, help = 'Bucket size of pixel rectangles X', sep = 0)
		self.gui_bucketsize_y   = GUI_Number('config', 'bucketsize_y',   'Y: ',       105, 1, 1000, default = 32, help = 'Bucket size of pixel rectangles Y')

		self.gui_error_filename = GUI_String('config', 'error_filename', '',                 440, 200, default = '>>gelato_log.txt', help = 'Error log file')
		self.gui_filename       = GUI_String('config', 'filename',       '',                 550, 200, default = filename,           help = 'File name')
		self.gui_path_inputs    = GUI_String('config', 'path_inputs',    'Path inputs: ',    650, 250, default = path_inputs,        help = 'Search path for scene files')
		self.gui_path_texture   = GUI_String('config', 'path_texture',   'Path texture: ',   650, 250, default = path_texture,       help = 'Search path for texture files')
		self.gui_path_shader    = GUI_String('config', 'path_shader',    'Path shader: ',    650, 250, default = path_shader,        help = 'Search path for compiled shaders')
		self.gui_path_imageio   = GUI_String('config', 'path_imageio',   'Path imageio: ',   650, 250, default = path_imageio,       help = 'Search path for image format input/output DSO\'s')
		self.gui_path_generator = GUI_String('config', 'path_generator', 'Path generator: ', 650, 250, default = path_generator,     help = 'Search path for generators DSO\'s')

		self.gui_preview_quality = GUI_Slider('config', 'preview_quality', 'Preview quality: ', 320, 0.0, 1.0, default = 0.1, help = 'Preview quality')

		self.gui_bucketorder = GUI_Menu('config', 'bucketorder', 100,
			'Bucket order', [
			['Horizontal', 'horizontal'],
			['Vertical',   'vertical'],
			['Spiral',     'spiral'],
			], default = 'Spiral', help = 'Render bucket order')

		self.gui_files_extensions = GUI_Menu('config', 'files_extensions', 130,
			'Files extensions', [
			['file.$FRAME.ext', 0],
			['file.ext.$FRAME', 1],
			], default = 'file.$FRAME.ext', help = 'Templates files extensions')

	def panel_output(self):

		self.gui_viewer.draw()
		self.gui_split.draw()
		self.gui_binary.draw()
		self.gui_relative_paths.draw()
		self.gui_pack_config.draw()

		GUI_Base.line_feed()

		GUI_Text.draw(self.color_text, 'Maximum threads:', 100, 2, 6)
		self.gui_auto.draw()

		if (not self.gui_auto.val):
			self.gui_limits_threads.draw()

		GUI_Base.line_feed()

		GUI_Text.draw(self.color_text, 'Bucket size:', 100, 2, 6)

		self.gui_bucketsize_x.draw()
		self.gui_bucketsize_y.draw()
		self.gui_bucketorder.draw()

		GUI_Base.line_feed()

		self.gui_anim.draw()

		if (self.gui_anim.val):
			self.gui_files_extensions.draw()

		GUI_Base.line_feed()

		self.gui_preview.draw()

		if (self.gui_preview.val):
			self.gui_preview_quality.draw()

		GUI_Base.line_feed()

		self.gui_error.draw()

		if (self.gui_error.val):
			self.gui_button_error.draw()
			self.gui_error_filename.draw()

		GUI_Base.line_feed()

		self.gui_button_filename.draw()
		self.gui_filename.draw()

		GUI_Base.line_feed()

		self.gui_path_inputs.draw()

		GUI_Base.line_feed()

		self.gui_path_texture.draw()

		GUI_Base.line_feed()

		self.gui_path_shader.draw()

		GUI_Base.line_feed()

		self.gui_path_imageio.draw()

		GUI_Base.line_feed()

		self.gui_path_generator.draw()

	def panel_images_init(self):

		self.gui_quantize_zero = GUI_String('config', 'quantize_zero', 'zero: ', 120, 20, default = '0',   help = 'Quantization parameter zero', sep = 0)
		self.gui_quantize_one  = GUI_String('config', 'quantize_one',  'one: ',  120, 20, default = '255', help = 'Quantization parameter one',  sep = 0)
		self.gui_quantize_min  = GUI_String('config', 'quantize_min',  'min: ',  120, 20, default = '0',   help = 'Quantization parameter min',  sep = 0)
		self.gui_quantize_max  = GUI_String('config', 'quantize_max',  'max: ',  120, 20, default = '255', help = 'Quantization parameter max')

		self.gui_gain           = GUI_Number('config', 'gain',           'Gain: ',   105, 0.0, 16.0,  default = 1.0,  help = 'Image gain')
		self.gui_gamma          = GUI_Number('config', 'gamma',          'Gamma: ',  105, 0.0, 16.0,  default = 1.0,  help = 'Image gamma')
		self.gui_antialiasing_x = GUI_Number('config', 'antialiasing_x', 'X: ',      110, 1,   32,    default = 4,    help = 'Spatial antialiasing X', sep = 0)
		self.gui_antialiasing_y = GUI_Number('config', 'antialiasing_y', 'Y: ',      110, 1,   32,    default = 4,    help = 'Spatial antialiasing Y')
		self.gui_filterwidth_x  = GUI_Number('config', 'filterwidth_x',  'X: ',      110, 0.0, 32.0,  default = 2.0,  help = 'Pixel filter width X', sep = 0)
		self.gui_filterwidth_y  = GUI_Number('config', 'filterwidth_y',  'Y: ',      110, 0.0, 32.0,  default = 2.0,  help = 'Pixel filter width Y')
		self.gui_dither         = GUI_Number('config', 'dither',         'Dither: ', 100, 0.0, 16.0,  default = 0.5,  help = 'Dither amplitude')

		self.gui_data = GUI_Menu('config', 'data', 105,
			'Output data', [
			['RGB',      ['rgb',  None]],
			['RGBA',     ['rgba', None]],
			['Z',        ['z',    None]],
			['RGB + Z',  ['rgb',  'z']],
			['RGBA + Z', ['rgba', 'z']],
			['AvgZ',     ['avgz', None]],
			['VolZ',     ['volz', None]],
			], default = 'RGB', help = 'Output data')

		w = 105

		gui_compression_tiff = GUI_Menu('config', 'compression_tiff', w,
			'TIFF compression', [
			['None', 'none'],
			['ZIP',  'zip'],
			['LZW',  'lzw'],
			], default = 'LZW', help = 'TIFF compression')

		gui_compression_openexr = GUI_Menu('config', 'compression_openexr', w,
			'OpenEXR compression', [
			['None',  'none'],
			['ZIP',   'zip'],
			['ZIPS',  'zips'],
			['PIZ',   'piz'],
			['PXR24', 'pxr24'],
			], default = 'ZIP', help = 'OpenEXR compression')

		self.gui_image_format = GUI_Menu('config', 'image_format', 105,
			'Image format', [
			['Null',    [None,	None,    None]],
			['TIFF',    ['tiff',	'.tif',  gui_compression_tiff]],
			['OpenEXR', ['OpenEXR', '.exr',  gui_compression_openexr]],
			['PNG',     ['png',	'.png',  None]],
			['JPEG',    ['jpg',	'.jpg',  None]],
			['TARGA',   ['targa',	'.tga',  None]],
			['PPM',     ['ppm',	'.ppm',  None]],
			['SGI',     ['DevIL',	'.sgi',  None]],
			['BMP',     ['DevIL',	'.bmp',  None]],
			['PCX',     ['DevIL',	'.pcx',  None]],
			['DDS',     ['DevIL',	'.dds',  None]],
			['RAW',     ['DevIL',	'.raw',  None]],
			['IFF',     ['iff',	'.iff',  None]],
			], default = 'TIFF', help = 'Output format')

		self.filters1 = [
			['Gaussian',        'gaussian'],
			['Box',             'box'],
			['Triangle',        'triangle'],
			['Catmull-Rom',     'catmull-rom'],
			['Sinc',            'sinc'],
			['Blackman-Harris', 'blackman-harris'],
			['Mitchell',        'mitchell'],
			['B-Spline',        'b-spline'],
		]

		self.filters2 = self.filters1[:]
		self.filters2.extend([
			['Min',     'min'],
			['Max',     'max'],
			['Average', 'average'],
		])

		self.gui_filters = GUI_Menu('config', 'filter', 105, options = self.filters2, default = 'Gaussian', help = 'Output format')

	def panel_images(self):

		self.gui_data.draw()
		self.gui_image_format.draw()

		compression = self.gui_image_format.val[2]
		if (compression):
			compression.draw()

		GUI_Base.line_feed()

		self.gui_gain.draw()
		self.gui_gamma.draw()

		GUI_Base.line_feed()

		GUI_Text.draw(self.color_text, 'Spatial antialiasing:', 105, 2, 6)

		self.gui_antialiasing_x.draw()
		self.gui_antialiasing_y.draw()

		GUI_Base.line_feed()

		GUI_Text.draw(self.color_text, 'Pixel filter width:', 105, 2, 6)

		self.gui_filterwidth_x.draw()
		self.gui_filterwidth_y.draw()

		if (self.gui_data.val[0] in ['rgb', 'rgba']):

			if (self.gui_filters.val in ['min', 'max', 'average']):
				self.gui_filters.setdefault()

			pixel_filters = self.filters1
		else:
			pixel_filters = self.filters2

		self.gui_filters.draw('Pixel filter', pixel_filters)

		GUI_Base.line_feed()

		if (self.gui_image_format.val[0] not in [None, 'OpenEXR']):

			GUI_Text.draw(self.color_text, 'Quantize:', 50, 2, 6)

			self.gui_quantize_zero.draw()
			self.gui_quantize_one.draw()
			self.gui_quantize_min.draw()
			self.gui_quantize_max.draw()
			self.gui_dither.draw()

	def panel_shadows_init(self):

		f = self.cb_shadows

		self.gui_shadow_maps       = GUI_Toggle('config', 'shadow_maps',       'Maps',       105, default = 0, func = f, help = 'Enable shadow maps', sep = 0)
		self.gui_shadow_woo        = GUI_Toggle('config', 'shadow_woo',        'Woo',        105, default = 0, func = f, help = 'Enable Woo (average) shadow')
		self.gui_shadow_ray_traced = GUI_Toggle('config', 'shadow_ray_traced', 'Ray traced', 105, default = 0, func = f, help = 'Enable ray traced shadows')
		self.gui_enable_dynamic    = GUI_Toggle('config', 'enable_dynamic',    'Dynamics',   210, default = 0,           help = 'Enable dynamic shadow')

		self.gui_ray_traced_shadow_bias = GUI_Number('config', 'ray_traced_shadow_bias', 'Shadow bias: ', 150, 0.0, 16.0, default = 0.01, help = 'Ray traced shadow bias')

		self.gui_compression_tiff = GUI_Menu('config', 'compression_shadow', 100,
			'TIFF compression', [
			['None', 'none'],
			['ZIP',  'zip'],
			['LZW',  'lzw'],
			], default = 'LZW', help = 'Shadow TIFF compression')

	def panel_shadows(self):

		self.gui_shadow_maps.draw()
		self.gui_shadow_woo.draw()
		self.gui_shadow_ray_traced.draw()

		if (self.gui_shadow_ray_traced.val):
			self.gui_ray_traced_shadow_bias.draw()

		if (self.gui_shadow_maps.val or self.gui_shadow_woo.val):

			GUI_Base.line_feed(False)

			self.gui_enable_dynamic.draw()

			if (not self.gui_enable_dynamic.val):

				GUI_Base.line_feed()

				self.gui_compression_tiff.draw()

	def panel_textures_init(self):

		texturefiles = ('100' if (WINDOWS) else '1000')

		self.gui_enable_textures    = GUI_Toggle('config', 'enable_textures',    'Enable',        100, default = 1, help = 'Enable all textures')
		self.gui_enable_automipmap  = GUI_Toggle('config', 'enable_automipmap',  'Auto mipmap',   100, default = 1, help = 'Automatically generate mipmap')
		self.gui_enable_textures_tx = GUI_Toggle('config', 'enable_textures_tx', 'Texture TX',    100, default = 0, help = 'Change the textures extension to .tx')
		self.gui_enable_autounpack  = GUI_Toggle('config', 'enable_autounpack',  'Auto unpack',   100, default = 0, help = 'Unpack and write temporary image texture')
		self.gui_enable_uv          = GUI_Toggle('config', 'enable_uv',          'Enable UV map', 100, default = 1, help = 'Enable UV mapping')
		self.gui_flip_u             = GUI_Toggle('config', 'flip_u',             'UV flip U',     100, default = 0, help = 'Enable UV flip U')
		self.gui_flip_v             = GUI_Toggle('config', 'flip_v',             'UV flip V',     100, default = 1, help = 'Enable UV flip V')
		self.gui_enable_uvlayes     = GUI_Toggle('config', 'enable_uvlayes',     'UV layers',     100, default = 0, help = 'Enable export UV layers')

		self.gui_limits_texturememory = GUI_String('config', 'limits_texturememory', 'Texture memory: ', 210, 30, default = '20480',      help = 'Maximum texture cache size in kB')
		self.gui_limits_texturefiles  = GUI_String('config', 'limits_texturefiles',  'Texture files:  ', 210, 30, default = texturefiles, help = 'Maximum number of open texture file')

	def panel_textures(self):

		if (self.gui_enable_textures.val):
			GUI_Text.draw(self.color_text, 'UV Col -> pretexture', 130, 2, 6)
			GUI_Base.line_feed()

		self.gui_enable_textures.draw()

		if (self.gui_enable_textures.val):

			self.gui_enable_automipmap.draw()
			self.gui_enable_textures_tx.draw()
			self.gui_enable_autounpack.draw()

			GUI_Base.line_feed()

			self.gui_enable_uv.draw()

			if (self.gui_enable_uv.val):

				self.gui_flip_u.draw()
				self.gui_flip_v.draw()
				self.gui_enable_uvlayes.draw()

			GUI_Base.line_feed()

			self.gui_limits_texturememory.draw()

			GUI_Base.line_feed()

			self.gui_limits_texturefiles.draw()

	def panel_stereo_init(self):

		self.gui_enable_stereo = GUI_Toggle('config', 'enable_stereo', 'Enable', 100, default = 0, help = 'Enable stereo rendering')

		self.gui_stereo_separation  = GUI_String('config', 'stereo_separation',  'Separation: ',  155, 30, default = '0', help = 'Camera separation for stereo cameras')
		self.gui_stereo_convergence = GUI_String('config', 'stereo_convergence', 'Convergence: ', 155, 30, default = '0', help = 'Convergence distance for stereo cameras')

		self.gui_stereo_projection = GUI_Menu('config', 'stereo_projection', 100,
			'Projection', [
			['Off-axis', 'off-axis'],
			['Parallel', 'parallel'],
			['Toe-in',   'toe-in'],
			], default = 'Off-axis', help = 'Projection for stereo cameras')

		self.gui_stereo_shade = GUI_Menu('config', 'stereo_shade', 100,
			'Shade', [
			['Left',   'left'],
			['Center', 'center'],
			['Right',  'right'],
			], default = 'Center', help = 'Which view to shade for stereo cameras')

	def panel_stereo(self):

		self.gui_enable_stereo.draw()

		if (self.gui_enable_stereo.val):

			self.gui_stereo_projection.draw()
			self.gui_stereo_shade.draw()
			self.gui_stereo_separation.draw()
			self.gui_stereo_convergence.draw()

	def panel_depth_of_field_init(self):

		self.gui_enable_dof = GUI_Toggle('config', 'enable_dof', 'Enable', 100, default = 0, help = 'Enable Depth Of Field')

		self.gui_dofquality = GUI_Number('config', 'dofquality', 'Quality: ', 100, 1, 256, default = 16, help = 'Number of lens values for DoF')

		self.gui_fstop       = GUI_String('config', 'fstop',       'F/Stop: ',       100, 20, default = '4.0',   help = 'F/Stop for depth of field')
		self.gui_focallength = GUI_String('config', 'focallength', 'Focal length: ', 160, 20, default = '0.032', help = 'Lens focal length')

	def panel_depth_of_field(self):

		self.gui_enable_dof.draw()

		if (self.gui_enable_dof.val):

			self.gui_fstop.draw()
			self.gui_focallength.draw()
			self.gui_dofquality.draw()

	def panel_motion_blur_init(self):

		self.gui_enable_motion_blur = GUI_Toggle('config', 'enable_motion_blur', 'Enable', 100, default = 0, help = 'Enable motion blur')

		self.gui_temporal_quality      = GUI_Number('config', 'temporal_quality',      'Quality: ',               100, 1,   256,    default = 16,  help = 'Number of time values for motion blur')
		self.gui_frames_transformation = GUI_Number('config', 'frames_transformation', 'Frames transformation: ', 180, 2,   9999,   default = 2,   help = 'Number of frames moion blur transformation')
		self.gui_frames_deformation    = GUI_Number('config', 'frames_deformation',    'Frames deformation: ',    180, 2,   9999,   default = 2,   help = 'Number of frames moion blur deformation')
		self.gui_dice_motionfactor     = GUI_Number('config', 'dice_motionfactor',     'Motion factor: ',         140, 0.0, 1000.0, default = 1.0, help = 'Scaling for decreased tessellation and shading for moving objects')

		self.gui_shutter_open  = GUI_String('config', 'shutter_open',  'Shutter open: ',  180, 20, default = '0.0', help = 'Shutter open time for motion blur')
		self.gui_shutter_close = GUI_String('config', 'shutter_close', 'Shutter close: ', 180, 20, default = '0.5', help = 'Shutter close time for motion blur')

	def panel_motion_blur(self):

		self.gui_enable_motion_blur.draw()

		if (self.gui_enable_motion_blur.val):

			self.gui_shutter_open.draw()
			self.gui_shutter_close.draw()

			GUI_Base.line_feed()

			self.gui_temporal_quality.draw()
			self.gui_frames_transformation.draw()
			self.gui_frames_deformation.draw()

			GUI_Base.line_feed()

			self.gui_dice_motionfactor.draw()

	def panel_ray_traced_init(self):

		self.gui_enable_ray_traced         = GUI_Toggle('config', 'enable_ray_traced',         'Enable',         100, default = 0, help = 'Enable ray traced reflections and refractions')
		self.gui_ray_traced_opaque_shadows = GUI_Toggle('config', 'ray_traced_opaque_shadows', 'Opaque shadows', 100, default = 1, help = 'Enable objects opaque regardless of their shaders')
		self.gui_ray_displace              = GUI_Toggle('config', 'ray_displace',              'Ray displace',   100, default = 1, help = 'Enable displace objects when ray tracing')
		self.gui_ray_motion                = GUI_Toggle('config', 'ray_motion',                'Ray motion',     100, default = 0, help = 'Do rays consider motion-blur of objects')

		self.gui_ray_traced_max_depth = GUI_Number('config', 'ray_traced_max_depth','Raytraced max depth: ', 210, 0, 32, default = 1, help = 'Ray traced max depth')

	def panel_ray_traced(self):

		self.gui_enable_ray_traced.draw()

		if (self.gui_enable_ray_traced.val):

			self.gui_ray_traced_max_depth.draw()

			GUI_Base.line_feed()

			self.gui_ray_traced_opaque_shadows.draw()
			self.gui_ray_displace.draw()
			self.gui_ray_motion.draw()

	def panel_displacement_init(self):

		self.gui_enable_displacements = GUI_Toggle('config', 'enable_displacements', 'Enable', 100, default = 0, help = 'Enable displacements')

		self.gui_maxradius = GUI_String('config', 'maxradius', 'Max radius: ', 140, 20, default = '0.0',    help = 'Maximum radial displacement')
		self.gui_maxspace  = GUI_String('config', 'maxspace',  'Max space: ',  140, 20, default = 'common', help = 'Coordinate system in which max radial displacement is measured')

	def panel_displacement(self):

		if (self.gui_enable_displacements.val):

			GUI_Text.draw(self.color_text, 'UV Disp -> dispmap | Disp -> Km', 130, 2, 6)
			GUI_Base.line_feed()

		self.gui_enable_displacements.draw()

		if (self.gui_enable_displacements.val):

			self.gui_maxradius.draw()
			self.gui_maxspace.draw()

	def panel_rerender_init(self):

		self.gui_enable_rerender = GUI_Toggle('config', 'enable_rerender', 'Enable', 100, default = 0, help = 'Enable the renderer in "re-render" mode')

		self.gui_rerender_memory = GUI_String('config', 'rerender_memory', 'Rerender memory: ', 210, 30, default = '', help = 'Size of re-render caches in KB')

	def panel_rerender(self):

		self.gui_enable_rerender.draw()

		if (self.gui_enable_rerender.val):
			self.gui_rerender_memory.draw()

	def panel_objects_init(self):

		w = 130

		self.gui_obj_excluded          = GUI_Toggle('local', None, 'Excluded',    w, func = self.cb_obj_excluded,          help = 'Excluded object exports')
		self.gui_obj_enable_postscript = GUI_Toggle('local', None, 'Post-script', w, func = self.cb_obj_enable_postscript, help = 'Enable object post-script')
		self.gui_obj_enable_prescript  = GUI_Toggle('local', None, 'Pre-script',  w, func = self.cb_obj_enable_prescript,  help = 'Enable object pre-script')

		self.gui_delete_all_properties = GUI_Button('local', None, 'Delete all properties', 130, func = self.cb_delete_all_properties, help = 'Delete all object\'s properties')

		self.gui_menu_obj_postscript = GUI_Menu('local', None, w, func = self.cb_menu_obj_postscript, help = 'Select object post-script')
		self.gui_menu_obj_prescript  = GUI_Menu('local', None, w, func = self.cb_menu_obj_prescript,  help = 'Select object pre-script')

	def panel_objects(self):

		self.gui_delete_all_properties.draw()

		GUI_Base.line_feed()

		obj = self.active_obj
		if (not obj):

			GUI_Text.draw(self.color_text, 'No object selected', 50, 2, 6)

		else:
			GUI_Text.draw(self.color_text,    'Object: ', 50, 2, 6, True)
			GUI_Text.draw(self.color_evident, '"%s"' % obj.name, 50, 2, 6, True)

			GUI_Base.line_feed()

			excluded = property_boolean_get(obj, 'excluded')
			self.gui_obj_excluded.draw(excluded)

			if (not excluded):

				if (self.gui_enable_scripts.val):

					texts = Blender.Text.Get()

					if (texts):

						list_texts = [[t.name, t.name] for t in texts]

						# post-script

						GUI_Base.line_feed()

						enable_postscript = property_boolean_get(obj, 'enable_postscript')
						self.gui_obj_enable_postscript.draw(enable_postscript)

						if (enable_postscript):

							script = property_string_get(obj, 'postscript')

							if (script):

								GUI_Text.draw(self.color_evident, script, 10, 2, 6)
							else:
								self.gui_menu_obj_postscript.draw('Load post-script from text', list_texts)

						# pre-script

						GUI_Base.line_feed(False)

						enable_prescript = property_boolean_get(obj, 'enable_prescript')
						self.gui_obj_enable_prescript.draw(enable_prescript)

						if (enable_prescript):

							script = property_string_get(obj, 'prescript')

							if (script):

								GUI_Text.draw(self.color_evident, script, 10, 2, 6)
							else:
								self.gui_menu_obj_prescript.draw('Load pre-script from text', list_texts)

	def panel_geometries_init(self):

		self.gui_enable_double_sided = GUI_Toggle('config', 'enable_double_sided', 'All double sided', 130, default = 0, help = 'Enable all double sided faces')
		self.gui_enable_dupli_verts  = GUI_Toggle('config', 'enable_dupli_verts',  'Dupli verts',      130, default = 1, help = 'Enable Dupli verts')
		self.gui_enable_vextex_color = GUI_Toggle('config', 'enable_vextex_color', 'Vextex color',     130, default = 1, help = 'Enable vextex color')
		self.gui_enable_halos        = GUI_Toggle('config', 'enable_halos',        'Halos',            130, default = 1, help = 'Enable halos (points)')

		self.gui_geo_catmull_clark     = GUI_Toggle('local', None, 'Catmull Clark',              130, func = self.cb_geo_catmull_clark,     help = 'Enable catmull-clark property')
		self.gui_geo_raster_width      = GUI_Toggle('local', None, 'Halo raster width',          130, func = self.cb_geo_raster_width,      help = 'Enable raster width (diameter of the point)')
		self.gui_geo_bake_diffuse      = GUI_Toggle('local', None, 'Bake diffuse',               130, func = self.cb_geo_bake_diffuse,      help = 'Enable bake diffuse property')
		self.gui_geo_indirect_light    = GUI_Toggle('local', None, 'Enable indirect',            130, func = self.cb_geo_indirect_light,    help = 'Enable indirect light')
		self.gui_geo_mb_transformation = GUI_Toggle('local', None, 'Motion blur transformation', 160, func = self.cb_geo_mb_transformation, help = 'Enable motion blur transformation')
		self.gui_geo_mb_deformation    = GUI_Toggle('local', None, 'Motion blur deformation',    160, func = self.cb_geo_mb_deformation,    help = 'Enable motion blur deformation')
		self.gui_geo_enable_proxy      = GUI_Toggle('local', None, 'Enable proxy',               130, func = self.cb_geo_enable_proxy,      help = 'Enable proxy file')

		self.gui_button_proxy_file = GUI_Button('local', None, 'Proxy file:', 100, func = self.cb_button_proxy_file, help = 'Select proxy file', sep = 0)

		self.gui_proxy_file = GUI_String('local', None, '', 410, 200, default = '', func = self.cb_proxy_file, help = 'Proxy file')

	def panel_geometries(self):

		obj_ok       = False
		excluded     = False
		enable_proxy = False

		obj = self.active_obj
		obj_ok = (obj and obj.type in ['Mesh', 'Surf'])
		if (obj_ok):

			excluded     = property_boolean_get(obj, 'excluded')
			enable_proxy = property_boolean_get(obj, 'enable_proxy')

			if (not excluded and enable_proxy):

				GUI_Text.draw(self.color_text, 'Proxy use only the first material assigned to the object', 130, 2, 6)

				GUI_Base.line_feed()

		self.gui_enable_double_sided.draw()
		self.gui_enable_dupli_verts.draw()
		self.gui_enable_vextex_color.draw()
		self.gui_enable_halos.draw()

		GUI_Base.line_feed()

		if (not obj_ok):

			GUI_Text.draw(self.color_text, 'No geometry selected', 50, 2, 6)
		else:
			excluded = property_boolean_get(obj, 'excluded')

#			GUI_Text.draw(self.color_text, 'Geometry: "%s"%s' % (obj.name, (' (excluded)' if excluded else '')), 50, 2, 6)

			GUI_Text.draw(self.color_text,    'Geometry: ', 50, 2, 6, True)
			GUI_Text.draw(self.color_evident, '"%s"' % obj.name, 50, 2, 6, True)
			if (excluded):
				GUI_Text.draw(self.color_text, ' (excluded)', 50, 2, 6, True)

			if (not excluded):

				GUI_Base.line_feed()

				catmull_clark  = property_boolean_get(obj, 'catmull_clark')
				self.gui_geo_catmull_clark.draw(catmull_clark)

				if (self.gui_enable_halos.val):

					raster_width = property_boolean_get(obj, 'raster_width')
					self.gui_geo_raster_width.draw(raster_width)

				if (self.gui_enable_bake_diffuse.val):

					bake_diffuse = property_boolean_get(obj, 'bake_diffuse')
					self.gui_geo_bake_diffuse.draw(bake_diffuse)

				if (self.gui_enable_indirect_light.val):

					indirect_light = property_boolean_get(obj, 'indirect_light', True)
					self.gui_geo_indirect_light.draw(indirect_light)

				if (self.gui_enable_motion_blur.val):

					GUI_Base.line_feed()

					motionblur_transformation = property_boolean_get(obj, 'motionblur_transformation', True)
					self.gui_geo_mb_transformation.draw(motionblur_transformation)

					motionblur_deformation = property_boolean_get(obj, 'motionblur_deformation')
					self.gui_geo_mb_deformation.draw(motionblur_deformation)

					GUI_Base.line_feed()

				GUI_Base.line_feed()

				self.gui_geo_enable_proxy.draw(enable_proxy)

				if (enable_proxy):

					proxy_file = property_string_get(obj, 'proxy_file')

					self.gui_button_proxy_file.draw()

					self.gui_proxy_file.draw(proxy_file)

	def panel_environment_init(self):

		w = 130

		self.gui_enable_sky = GUI_Toggle('config', 'enable_sky', 'Sky', w, default = 1, help = 'Enable background color')

		self.gui_enable_world_postscript = GUI_Toggle('config', 'enable_world_postscript', 'Post-script', w, default = 0, func = self.cb_enable_world_postscript, help = 'Enable world post-script')
		self.gui_enable_world_prescript  = GUI_Toggle('config', 'enable_world_prescript',  'Pre-script',  w, default = 0, func = self.cb_enable_world_prescript,  help = 'Enable world pre-script')

		self.gui_world_postscript = GUI_String('config', 'world_postscript', '', 0, 0, default = '')
		self.gui_world_prescript  = GUI_String('config', 'world_prescript',  '', 0, 0, default = '')

		self.gui_units_lengthscale = GUI_String('config', 'units_lengthscale', 'Length scale: ', 130, 20, default = '1.0', help = 'Length unit scale of "common" space units')

		self.gui_menu_world_postscript = GUI_Menu('local', None, w, func = self.cb_menu_world_postscript, help = 'Select world post-script')
		self.gui_menu_world_prescript  = GUI_Menu('local', None, w, func = self.cb_menu_world_prescript,  help = 'Select world pre-script')

		self.gui_units_length = GUI_Menu('config', 'units_length', 90,
			'Units', [
			['None',       None],
			['Millimeter', 'mm'],
			['Centimeter', 'cm'],
			['Meter',      'm'],
			['Kilometer',  'km'],
			['Inch',       'in'],
			['Foot',       'ft'],
			['Mile',       'mi'],
			], default = 'None', help = 'Physical length units of "common" space')

	def panel_environment(self):

		self.gui_enable_sky.draw()

		GUI_Text.draw(self.color_text, 'Units:', 30, 2, 6)

		self.gui_units_length.draw()

		if (self.gui_units_length.val):
			self.gui_units_lengthscale.draw()

		if (self.gui_enable_scripts.val):

			texts = Blender.Text.Get()

			if (texts):

				list_texts = [[t.name, t.name] for t in texts]

				# post-script

				GUI_Base.line_feed()

				self.gui_enable_world_postscript.draw()

				if (self.gui_enable_world_postscript.val):

					script = self.gui_world_postscript.val

					if (script):

						GUI_Text.draw(self.color_evident, script, 10, 2, 6)
					else:
						self.gui_menu_world_postscript.draw('Load post-script from text', list_texts)

				# pre-script

				GUI_Base.line_feed(False)

				self.gui_enable_world_prescript.draw()

				if (self.gui_enable_world_prescript.val):

					script = self.gui_world_prescript.val

					if (script):

						GUI_Text.draw(self.color_evident, script, 10, 2, 6)
					else:
						self.gui_menu_world_prescript.draw('Load pre-script from text', list_texts)

	def panel_scripts_init(self):

		w = 130

		self.gui_enable_scripts = GUI_Toggle('config', 'enable_scripts', 'Enable', w, default = 1, help = 'Enable scripts')

		self.gui_enable_header_postscript = GUI_Toggle('config', 'enable_header_postscript', 'Post-script', w, default = 0, func = self.cb_enable_header_postscript, help = 'Enable header post-script')
		self.gui_enable_header_prescript  = GUI_Toggle('config', 'enable_header_prescript',  'Pre-script',  w, default = 0, func = self.cb_enable_header_prescript,  help = 'Enable header pre-script')

		self.gui_header_postscript = GUI_String('config', 'header_postscript', '', 0, 0, default = '')
		self.gui_header_prescript  = GUI_String('config', 'header_prescript',  '', 0, 0, default = '')

		self.gui_menu_header_postscript = GUI_Menu('local', None, w, func = self.cb_menu_header_postscript, help = 'Select header post-script')
		self.gui_menu_header_prescript  = GUI_Menu('local', None, w, func = self.cb_menu_header_prescript,  help = 'Select header pre-script')

	def panel_scripts(self):

		self.gui_enable_scripts.draw()

		if (self.gui_enable_scripts.val):

			texts = Blender.Text.Get()

			if (texts):

				list_texts = [[t.name, t.name] for t in texts]

				# post-script

				GUI_Base.line_feed()

				self.gui_enable_header_postscript.draw()

				if (self.gui_enable_header_postscript.val):

					script = self.gui_header_postscript.val

					if (script):

						GUI_Text.draw(self.color_evident, script, 10, 2, 6)
					else:
						self.gui_menu_header_postscript.draw('Load post-script from text', list_texts)

				# pre-script

				GUI_Base.line_feed(False)

				self.gui_enable_header_prescript.draw()

				if (self.gui_enable_header_prescript.val):

					script = self.gui_header_prescript.val

					if (script):

						GUI_Text.draw(self.color_evident, script, 10, 2, 6)
					else:
						self.gui_menu_header_prescript.draw('Load pre-script from text', list_texts)

	def panel_shaders_init(self):

		w = 130

		self.gui_enable_shaders = GUI_Toggle('config', 'enable_shaders', 'Enable', 130, default = 1, help = 'Enable all shaders')

		self.gui_mat_enable_postscript = GUI_Toggle('local', None, 'Post-script', w, func = self.cb_mat_enable_postscript, help = 'Enable shader post-script')
		self.gui_mat_enable_script     = GUI_Toggle('local', None, 'Script',      w, func = self.cb_mat_enable_script,     help = 'Enable shader script')
		self.gui_mat_enable_prescript  = GUI_Toggle('local', None, 'Pre-script',  w, func = self.cb_mat_enable_prescript,  help = 'Enable shader pre-script')

		self.gui_enable_shader_debug = GUI_Toggle('local', 'enable_shader_debug', 'Enable debug', 130, default = 0, func = self.cb_enable_shader_debug, help = 'Enable debug shaders')

		self.gui_shadingquality  = GUI_Number('config', 'shadingquality',  'Shading quality: ', 160, 0.0, 16.0, default = 1.0, help = 'Shading quality')
		self.gui_limits_gridsize = GUI_Number('config', 'limits_gridsize', 'Limits gridsize: ', 150, 1,   1024, default = 256, help = 'Maximum number of surface points at one time')

		self.gui_button_mat_assign = GUI_Button('local', None, 'Assign', 130, func = self.cb_button_mat_assign, help = 'Assign material')
		self.gui_button_mat_remove = GUI_Button('local', None, 'Remove', 130, func = self.cb_button_mat_remove, help = 'Remove assign')

		self.gui_menu_shader_debug = GUI_Menu('local', None, 160, func = self.cb_menu_shader_debug, help = 'Select shader debug')
		self.gui_menu_shader       = GUI_Menu('local', None, 130, func = self.cb_menu_shader,       help = 'Select shader')
		self.gui_menu_material     = GUI_Menu('local', None, 130, help = 'Select material')

		self.gui_menu_mat_postscript = GUI_Menu('local', None, w, func = self.cb_menu_mat_postscript, help = 'Select shader post-script')
		self.gui_menu_mat_script     = GUI_Menu('local', None, w, func = self.cb_menu_mat_script,     help = 'Select shader script')
		self.gui_menu_mat_prescript  = GUI_Menu('local', None, w, func = self.cb_menu_mat_prescript,  help = 'Select shader pre-script')

	def panel_shaders(self):

		enable_script  = False
		enable_shaders = self.gui_enable_shaders.val

		if (enable_shaders):

			GUI_Text.draw(self.color_text, 'Col -> C | A -> opacity', 130, 2, 6)

			GUI_Base.line_feed()

		self.gui_enable_shaders.draw()

		if (enable_shaders):

			self.gui_shadingquality.draw()
			self.gui_limits_gridsize.draw()

			GUI_Base.line_feed()

			self.gui_enable_shader_debug.draw()

			if (self.gui_enable_shader_debug.val and self.list_shaders_debug):

				self.gui_menu_shader_debug.draw('Debug shaders', self.list_shaders_debug)

				if (self.shader_debug is not None):

					GUI_Base.line_feed()

					self.shader_debug.draw()

			elif (self.list_shaders_surface):

				# get all materials

				materials = Blender.Material.Get()

				if (materials):

					list_materials = [[m.name, m.name] for m in sorted(materials)]

					material_name = self.gui_menu_material.val

					if (self.gui_enable_scripts.val and list_materials and (material_name is not None)):

						self.active_mat = mat = Blender.Material.Get(material_name)

						if (mat is not None):

							texts = Blender.Text.Get()

							if (texts):

								list_texts = [[t.name, t.name] for t in texts]

								# post-script

								GUI_Base.line_feed()

								enable_postscript = property_boolean_get(mat, 'enable_postscript')
								self.gui_mat_enable_postscript.draw(enable_postscript)

								if (enable_postscript):

									script = property_string_get(mat, 'postscript')

									if (script):

										GUI_Text.draw(self.color_evident, script, 10, 2, 6)
									else:
										self.gui_menu_mat_postscript.draw('Load post-script from text', list_texts)

								# script

								GUI_Base.line_feed(False)

								enable_script = property_boolean_get(mat, 'enable_script')
								self.gui_mat_enable_script.draw(enable_script)

								if (enable_script):

									script = property_string_get(mat, 'script')

									if (script):

										GUI_Text.draw(self.color_evident, script, 10, 2, 6)
									else:
										self.gui_menu_mat_script.draw('Load script from text', list_texts)

								# pre-script

								GUI_Base.line_feed(False)

								enable_prescript = property_boolean_get(mat, 'enable_prescript')
								self.gui_mat_enable_prescript.draw(enable_prescript)

								if (enable_prescript):

									script = property_string_get(mat, 'prescript')

									if (script):

										GUI_Text.draw(self.color_evident, script, 10, 2, 6)
									else:
										self.gui_menu_mat_prescript.draw('Load pre-script from text', list_texts)

					# materials assign

					if (not enable_script):

						self.draw_shader_help()

						GUI_Base.line_feed()

						self.gui_menu_material.draw('Materials', list_materials)

						self.shader_surface = sd = self.assigned_material[1].get(material_name)
						if (sd is None):

							self.gui_button_mat_assign.draw()
							self.gui_menu_shader.draw('Shaders', self.list_shaders_surface)
						else:

							self.gui_button_mat_remove.draw()


							if (self.gui_enable_bake_diffuse.val):

								GUI_Base.line_feed()

								sd.draw_sss()

							GUI_Base.line_feed()

							sd.draw()

	def panel_lights_init(self):

		w = 130

		self.gui_lamp_photon_map = GUI_Toggle('local', None, 'Photon map', 130, func = self.cb_lamp_photon_map, help = 'Enable photon map property')

		self.gui_lamp_enable_postscript = GUI_Toggle('local', None, 'Post-script', w, func = self.cb_lamp_enable_postscript, help = 'Enable lamp post-script')
		self.gui_lamp_enable_script     = GUI_Toggle('local', None, 'Script',      w, func = self.cb_lamp_enable_script,     help = 'Enable lamp script')
		self.gui_lamp_enable_prescript  = GUI_Toggle('local', None, 'Pre-script',  w, func = self.cb_lamp_enable_prescript,  help = 'Enable lamp pre-script')

		self.gui_enable_lights       = GUI_Toggle('config', 'enable_lights',       'Enable',       130, default = 1, help = 'Enable all lights')
		self.gui_enable_key_fill_rim = GUI_Toggle('config', 'enable_key_fill_rim', 'Key Fill Rim', 130, default = 0, help = 'Enable Key-Fill-Rim lights')

		self.gui_button_lamp_assign = GUI_Button('local', None, 'Assign', 130, func = self.cb_button_lamp_assign, help = 'Assign lamp')
		self.gui_button_lamp_remove = GUI_Button('local', None, 'Remove', 130, func = self.cb_button_lamp_remove, help = 'Remove assign')

		self.gui_lights_factor = GUI_Slider('config', 'lights_factor', 'Lights factor: ', 320, 0.0, 1000.0, default = 50.0, help = 'Lights factor')

		self.gui_menu_light = GUI_Menu('local', None, 130, func = self.cb_gui_menu_light, help = 'Select shader')
		self.gui_menu_lamp  = GUI_Menu('local', None, 130, help = 'Select lamp')

		self.gui_menu_lamp_postscript = GUI_Menu('local', None, w, func = self.cb_menu_lamp_postscript, help = 'Select lamp post-script')
		self.gui_menu_lamp_script     = GUI_Menu('local', None, w, func = self.cb_menu_lamp_script,     help = 'Select lamp script')
		self.gui_menu_lamp_prescript  = GUI_Menu('local', None, w, func = self.cb_menu_lamp_prescript,  help = 'Select lamp pre-script')

	def panel_lights(self):

		enable_script = False
		enable_lights = self.gui_enable_lights.val

		if (enable_lights):

			GUI_Text.draw(self.color_text, 'Amb -> ambientlight | Lamp -> pointlight | Spot -> spotlight | Sun -> distantlight', 130, 2, 6)

			GUI_Base.line_feed()

		self.gui_enable_lights.draw()
		self.gui_enable_key_fill_rim.draw()

		if (enable_lights):

			self.gui_lights_factor.draw()

			GUI_Base.line_feed()

			obj = self.active_obj
			obj_ok = (obj and (obj.type == 'Lamp'))
			if (not obj_ok):

				GUI_Text.draw(self.color_text, 'No lamp selected', 50, 2, 6)
			else:
				excluded = property_boolean_get(obj, 'excluded')

				GUI_Text.draw(self.color_text,    'Lamp: ', 50, 2, 6, True)
				GUI_Text.draw(self.color_evident, '"%s"' % obj.name, 50, 2, 6, True)
				if (excluded):
					GUI_Text.draw(self.color_text, ' (excluded)', 50, 2, 6, True)

				if (not excluded):

					if (self.gui_enable_caustics.val):

						GUI_Base.line_feed()

						photon_map = property_boolean_get(obj, 'photon_map')
						self.gui_lamp_photon_map.draw(photon_map)

				if (self.gui_enable_scripts.val):

					texts = Blender.Text.Get()

					if (texts):

						list_texts = [[t.name, t.name] for t in texts]

						# post-script

						GUI_Base.line_feed()

						enable_postscript = property_boolean_get(obj, 'enable_postscript')
						self.gui_lamp_enable_postscript.draw(enable_postscript)

						if (enable_postscript):

							script = property_string_get(obj, 'postscript')

							if (script):

								GUI_Text.draw(self.color_evident, script, 10, 2, 6)
							else:
								self.gui_menu_lamp_postscript.draw('Load post-script from text', list_texts)

						# script

						GUI_Base.line_feed(False)

						enable_script = property_boolean_get(obj, 'enable_script')
						self.gui_lamp_enable_script.draw(enable_script)

						if (enable_script):

							script = property_string_get(obj, 'script')

							if (script):

								GUI_Text.draw(self.color_evident, script, 10, 2, 6)
							else:
								self.gui_menu_lamp_script.draw('Load script from text', list_texts)

						# pre-script

						GUI_Base.line_feed(False)

						enable_prescript = property_boolean_get(obj, 'enable_prescript')
						self.gui_lamp_enable_prescript.draw(enable_prescript)

						if (enable_prescript):

							script = property_string_get(obj, 'prescript')

							if (script):

								GUI_Text.draw(self.color_evident, script, 10, 2, 6)
							else:
								self.gui_menu_lamp_prescript.draw('Load pre-script from text', list_texts)

			if (self.list_shaders_light and (not enable_script)):

				# get all lamps

				lamps = Blender.Lamp.Get()

				if (lamps):

					list_lamps = [[l.name, l.name] for l in sorted(lamps)]

					lamp_name = self.gui_menu_lamp.val

					# lights assign

					self.draw_shader_help()

					GUI_Base.line_feed()

					self.gui_menu_lamp.draw('Lamps', list_lamps)

					self.shader_light = sd = self.assigned_light[1].get(lamp_name)
					if (sd is None):

						self.gui_button_lamp_assign.draw()
						self.gui_menu_light.draw('Shaders', self.list_shaders_light)
					else:
						self.gui_button_lamp_remove.draw()

						if (self.gui_shadow_maps.val or self.gui_shadow_woo.val or self.gui_shadow_ray_traced.val):

							GUI_Base.line_feed()

							sd.gui_shadow()

						GUI_Base.line_feed()

						sd.draw()

	def panel_caustics_init(self):

		self.gui_enable_caustics = GUI_Toggle('config', 'enable_caustics', 'Enable', 100, default = 0, help = 'Enable caustics')

		self.gui_caustics_max_depth = GUI_Number('config', 'caustics_max_depth', 'Raytraced max depth: ', 180, 0, 32, default = 4, help = 'Ray traced max depth caustics')

	def panel_caustics(self):
		enable_caustics = self.gui_enable_caustics.val

		if (enable_caustics):

			GUI_Text.draw(self.color_text, 'IOR -> eta | specTransp -> Kt | rayMirr -> Kr | diffuseSize -> Kd | specSize -> Ks | roughness -> roughness', 130, 2, 6)

			GUI_Base.line_feed(False)

			GUI_Text.draw(self.color_text, 'spec color -> specularcolor | mir color -> transmitcolor', 130, 2, 6)

			GUI_Base.line_feed()

		self.gui_enable_caustics.draw()


		if (enable_caustics):

			self.gui_caustics_max_depth.draw()

			shader_shoot_photons = self.assigned_material[0].get('shoot_photons')
			if (shader_shoot_photons is not None):

				GUI_Base.line_feed()

				shader_shoot_photons.draw()

			shader_caustic_light = self.assigned_light[0].get('caustic_light')
			if (shader_caustic_light is not None):

				GUI_Base.line_feed()

				shader_caustic_light.draw()

	def panel_ambient_occlusion_init(self):

		self.gui_enable_ambient_occlusion = GUI_Toggle('config', 'enable_ambient_occlusion', 'Enable', 100, default = 0, help = 'Enable ambient occlusion')

	def panel_ambient_occlusion(self):
		self.gui_enable_ambient_occlusion.draw()

		if (self.gui_enable_ambient_occlusion.val):

			shader_ambient_occlusion = self.assigned_material[0].get('ambient_occlusion')
			if (shader_ambient_occlusion is not None):

				GUI_Base.line_feed()

				shader_ambient_occlusion.draw()

			shader_environment_light = self.assigned_light[0].get('environment_light')
			if (shader_environment_light is not None):

				GUI_Base.line_feed()

				shader_environment_light.draw()

	def panel_indirect_light_init(self):

		self.gui_enable_indirect_light = GUI_Toggle('config', 'enable_indirect_light', 'Enable', 100, default = 0, help = 'Enable indirect light')

		self.gui_indirect_minsamples = GUI_Number('config', 'indirect_minsamples','Min samples: ', 140, 0, 16, default = 3, help = 'The minimum number of nearby samples')

	def panel_indirect_light(self):
		self.gui_enable_indirect_light.draw()

		if (self.gui_enable_indirect_light.val):

			shader_indirect_light = self.assigned_light[0].get('indirect_light')
			if (shader_indirect_light is not None):

				self.gui_indirect_minsamples.draw()

				GUI_Base.line_feed()

				shader_indirect_light.draw()

	def panel_sss_init(self):

		self.gui_enable_bake_diffuse = GUI_Toggle('config', 'enable_bake_diffuse', 'Enable', 100, default = 0, help = 'Enable bake diffuse')

	def panel_sss(self):
		self.gui_enable_bake_diffuse.draw()

		if (self.gui_enable_bake_diffuse.val):

			shader_bake_diffuse = self.assigned_material[0]['bake_diffuse']

			if (shader_bake_diffuse is not None):

				GUI_Base.line_feed()

				shader_bake_diffuse.draw()

	def config_save(self):

		# write xml file

		dom = xml.dom.minidom.getDOMImplementation()
		doctype = dom.createDocumentType(ROOT_ELEMENT, None, None)

		doc = dom.createDocument(None, ROOT_ELEMENT, doctype )

		root = doc.documentElement
		doc.appendChild(root)

		root.setAttribute('version', __version__)
		root.setAttribute('timestamp', datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S'))
		root.setAttribute('scene', Blender.Scene.GetCurrent().name)

		try:
			root.setAttribute('user', getpass.getuser())
			root.setAttribute('hostname', socket.gethostname())
		except:
			pass

		root.setAttribute('blender', str(Blender.Get('version')))
		root.setAttribute('platform', sys.platform)

		head = doc.createElement('config')
		root.appendChild(head)

		config = [(g.name, g.internal_val) for g in GUI_Base.registry('config') if g.name is not None]
		config.sort(cmp = lambda a, b: cmp(a[0], b[0]))

		for (name, value) in config:

			elem = doc.createElement(name)
			head.appendChild(elem)
			elem.appendChild(doc.createTextNode(str(value).strip()))

		sc = Blender.Scene.GetCurrent()

		for (name, value) in [(g.name, g.internal_val) for g in GUI_Base.registry('blend') if g.name is not None]:
			property_set(sc, name, value)

		# materials

		blender_materials = [m.name for m in Blender.Material.Get()]

		for (idx, ml) in enumerate(self.assigned_material):

			materials = doc.createElement('materials')
			root.appendChild(materials)
			materials.setAttribute('index', str(idx))

			for (mat, sd) in sorted(ml.iteritems()):

				if (((idx > 0) and (mat not in blender_materials)) or (sd is None)):
					continue

				material = doc.createElement('material')
				materials.appendChild(material)
				material.setAttribute('name', mat)

				if ((idx > 0) and (sd.enable_sss)):
					material.setAttribute('enable_sss', str(int(sd.enable_sss)))
					material.setAttribute('sss_parameter', sd.sss)

				sd.toxml(doc, material)

		# lights

		for (idx, lg) in enumerate(self.assigned_light):

			lights = doc.createElement('lights')
			root.appendChild(lights)
			lights.setAttribute('index', str(idx))

			for (lig, sd) in sorted(lg.iteritems()):

				if (sd is None):
					continue

				light = doc.createElement('light')
				lights.appendChild(light)
				light.setAttribute('name', lig)

				if ((idx > 0) and (sd.enable_shadow)):
					light.setAttribute('enable_shadow', str(int(sd.enable_shadow)))
					light.setAttribute('shadow_parameter', sd.shadow)

				sd.toxml(doc, light)

		if (property_boolean_get(sc, 'pack_config')):

			# delete text file

			try:
				Blender.Text.unlink(Blender.Text.Get(self.config_filename))
			except:
				pass

			# add text file

			try:
				text = Blender.Text.New(self.config_filename)

				if (USE_XML_DOM_EXT):
					xml.dom.ext.PrettyPrint(doc, text)
				else:
					text.write(doc.toprettyxml(indent = '  ', newl = '\n'))
			except:
				sys.excepthook(*sys.exc_info())

		else:
			try:
				fxml = OpenTempRename(self.config_filename, 'w')

			except IOError:

				print 'Error: Cannot write file "%s"' % self.config_filename
				return

			except:
				sys.excepthook(*sys.exc_info())
				return

			# write file

			try:
				if (USE_XML_DOM_EXT):
					xml.dom.ext.PrettyPrint(doc, fxml.fd)
				else:
					doc.writexml(fxml.fd, addindent = '  ', newl = '\n')
			except:
				sys.excepthook(*sys.exc_info())

	def config_load(self):

		sc = Blender.Scene.GetCurrent()

		for (name, gui) in [(g.name, g) for g in GUI_Base.registry('blend') if g.name is not None]:

			try:
				val = property_get(sc, name)
			except:
				continue

			try:
				ty = gui.internal_type

				if (ty is int):
					gui.internal_val = int(val)
				elif (ty is float):
					gui.internal_val = float(val)
				elif (ty is str):
					gui.internal_val = str(val)
				else:
					print 'Error: file "%s", element "%s" type "%s" unknow' % (self.config_filename, name, ty)
			except:
				sys.excepthook(*sys.exc_info())

		if (property_boolean_get(sc, 'pack_config')):

			# read pack xml file

			try:
				text = Blender.Text.Get(self.config_filename)
				doc = xml.dom.minidom.parseString(''.join(text.asLines()))

			except:
				print 'Info: XML config "%s" not found, will use default settings' % self.config_filename
				return

		else:
			try:
				doc = xml.dom.minidom.parse(self.config_filename)
			except:
				print 'Info: XML config file "%s" not found, will use default settings' % self.config_filename
				return

		if (doc.documentElement.tagName != ROOT_ELEMENT):
			print 'Error: file "%s", invalid root element "%s"' % (self.config_filename, doc.documentElement.tagName)
			return

		head = doc.getElementsByTagName('config')
		if (len(head) == 0):

			print 'Error: file "%s", not element "config"' % self.config_filename
		else:

			config = [(g.name, g) for g in GUI_Base.registry('config') if g.name is not None]

			for (name, gui) in config:

				el = head[0].getElementsByTagName(name)
				if (len(el) == 0):
					continue

				el[0].normalize()
				nd = el[0].firstChild
				if (nd.nodeType != xml.dom.Node.TEXT_NODE):
					continue

				try:
					ty = gui.internal_type

					if (ty is int):
						gui.internal_val = int(nd.data)
					elif (ty is float):
						gui.internal_val = float(nd.data)
					elif (ty is str):
						gui.internal_val = str(nd.data.strip())
					else:
						print 'Error: file "%s", element "%s" type "%s" unknow' % (self.config_filename, name, ty)
				except:
					sys.excepthook(*sys.exc_info())

		# materials

		blender_materials = [m.name for m in Blender.Material.Get()]

		for material in doc.getElementsByTagName('materials'):

			index = material.getAttribute('index')
			if (index is None):
				print 'Error: file "%s", not attribute "index" element "materials"' % self.config_filename
				continue

			idx = int(index)

			for mat in material.getElementsByTagName('material'):

				name = mat.getAttribute('name')
				if (name is None):
					continue

				if ((idx > 0) and (name not in blender_materials)):
					continue

				sd = Shader()

				if (not sd.fromxml(mat)):
					continue

				try:
					enable_sss = mat.getAttribute('enable_sss')
					if (enable_sss):
						sd.enable_sss = int(enable_sss)
				except:
					sys.excepthook(*sys.exc_info())

				try:
					sss_parameter = mat.getAttribute('sss_parameter')
					if (sss_parameter):
						sd.sss = str(sss_parameter).strip()
				except:
					sys.excepthook(*sys.exc_info())

				self.assigned_material[idx][name] = sd

		# lights

		for light in doc.getElementsByTagName('lights'):

			index = light.getAttribute('index')
			if (index is None):
				print 'Error: file "%s", not attribute "index" element "lights"' % self.config_filename
				continue

			idx = int(index)

			for lig in light.getElementsByTagName('light'):

				name = lig.getAttribute('name')
				if (name is None):
					continue

				sd = Shader()

				if (not sd.fromxml(lig)):
					continue

				try:
					enable_shadow = lig.getAttribute('enable_shadow')
					if (enable_shadow):
						sd.enable_shadow = int(enable_shadow)
				except:
					sys.excepthook(*sys.exc_info())

				try:
					shadow_parameter = lig.getAttribute('shadow_parameter')
					if (shadow_parameter):
						sd.shadow = str(shadow_parameter).strip()
				except:
					sys.excepthook(*sys.exc_info())

				self.assigned_light[idx][name] = sd

# property

def property_set(obj, name, value):

	def __property_set(obj, name, value):
		try:
			if (obj.properties.has_key('gelato')):
				obj.properties['gelato'][name] = value
			else:
				obj.properties['gelato'] = {name: value}
		except:
			sys.excepthook(*sys.exc_info())

	if (type(obj) is list):
		for x in obj:
			__property_set(x, name, value)
	else:
		__property_set(obj, name, value)

def property_get(obj, name):
	return obj.properties['gelato'][name]

def property_boolean_get(obj, name, default = False):
	try:
		return property_get(obj, name) != 0
	except KeyError:
		return default

def property_string_get(obj, name, default = ''):
	try:
		return property_get(obj, name)
	except KeyError:
		return default

def selected_object(types = None):
	selected = Blender.Object.GetSelected()
	if (selected):
		obj = selected[0]
		if (types is None):
			return obj
		if (obj.type in types):
			return obj
	return None

# utility

def clamp(v, vmin, vmax):
	if (v < vmin):
		return vmin
	if (v > vmax):
		return vmax
	return v

def space2underscore(name):
	# replace spaces to '_'
	return re.sub('\s+', '_', name)

def fix_file_name(filename):
	if (os.path.sep == '\\'):
		# replace '\' to '\\'
		return filename.replace('\\', '\\\\')
	return filename

def fix_vars(name):
	if (WINDOWS):
		# replace $var to %var%
		return re.sub('\$(\w+)', '%\\1%', name)
	return name

def search_file(name, paths):
	for p in paths.split(':'):
		try:
			path = os.path.expandvars(p)
			filename = os.path.join(path, name)
			if (os.path.exists(filename)):
				return filename
		except:
			continue
	return None

def find_files(pattern, paths):
	fdict = {}
	for p in paths.split(':'):
		try:
			path = os.path.expandvars(p)
			files = os.listdir(path)
			for f in fnmatch.filter(files, pattern):
				fdict[f] = path
		except:
			continue
	return fdict

# main

def main():
	global GELATO, GSOINFO, MAKETX
	global ROOT_ELEMENT, INTERACTIVE, CMD_MASK
	global gelato_gui, pyg

	print 'Info: Blendergelato version', __version__

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 5

	if (sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR)):
		raise ('Error: Python version %d.%d or greater is required\nPython version is %s' % (PYTHON_MAJOR, PYTHON_MINOR, sys.version))

	ROOT_ELEMENT = 'BlenderGelato'

	# blender's mode

	INTERACTIVE = Blender.mode == 'interactive'

	# programs

	CMD_MASK = ('""%s" "%s""' if (WINDOWS) else '"%s" "%s"')

	GELATO	= 'gelato'
	GSLC    = 'gslc'
	GSOINFO = 'gsoinfo'
	MAKETX	= 'maketx'

	if (WINDOWS):
		exe = '.exe'
		GELATO	+= exe
		GSLC    += exe
		GSOINFO += exe
		MAKETX	+= exe

	gelatohome = os.getenv('GELATOHOME')
	if (gelatohome):
		print 'Info: GELATOHOME = "%s"' % gelatohome

		bin = os.path.join(gelatohome, 'bin')

		GELATO	= fix_file_name(os.path.join(bin, GELATO))
		GSLC	= fix_file_name(os.path.join(bin, GSLC))
		GSOINFO = fix_file_name(os.path.join(bin, GSOINFO))
		MAKETX	= fix_file_name(os.path.join(bin, MAKETX))
	else:
		print 'Info: GELATOHOME environment variable not set'

	# gelato convert

	pyg = Gelato_pyg()

	# GUI

	gelato_gui = GUI_Config()

	# rename old config file

	try:
		filename = gelato_gui.config_filename
		filename_old = filename + '.old'

		if (os.path.exists(filename)):
			shutil.copyfile(filename, filename_old)
	except:
		sys.excepthook(*sys.exc_info())

	# load and save config file

	gelato_gui.config_load()
	gelato_gui.config_save()

	# start

	if (INTERACTIVE):
		# display GUI
		Blender.Draw.Register(gelato_gui.draw, gelato_gui.handle_event, gelato_gui.handle_button_event)
	else:
		# export scene
		gelato_gui.cb_save(0, 0)

		# export scene and run Gelato
#		gelato_gui.cb_render(0)

if __name__ == '__main__':
	try:
		import psyco
		psyco.full()
#		psyco.log()
#		psyco.profile()
	except:
		pass

#	import pycallgraph
#	pycallgraph.start_trace()

	main()

#	pycallgraph.make_dot_graph('/tmp/gelato.pdf', format='pdf')

