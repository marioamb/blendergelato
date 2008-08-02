#!BPY
#coding=utf-8

"""
Name: 'Blender Gelato'
Blender: 245
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato(TM)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.18k'
__url__ = ['http://code.google.com/p/blendergelato/source/browse/trunk/blendergelato.py']
__bpydoc__ = """\
Blender(TM) to NVIDIA Gelato(TM) scene converter
"""

# NVIDIA Gelato(TM) Exporter
#
# Original By: Mario Ambrogetti
# Date:        Sun, 20 Jul 2008 09:45:21 +0200
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
import datetime, fnmatch
import math, copy, re
import tempfile, ctypes
import getpass, socket
import xml.dom.minidom

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

class enum_type(object):
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

class open_temp_rename(object):
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
		global WINDOWS

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

class progress_bar(object):
	__slots__ = ['width', 'count_min', 'count_max', 'message', 'length', 'buffer', \
			'convert', 'middle', 'enable_percent', 'percent', 'first',]

	def __init__(self, width):
		"""
		Progress bar for Blebder's GUI or ASCII-art
		"""

		self.width = (2 if (width < 2) else width - 2)

		self.setup()

	def setup(self, count_min = 0, count_max = 0, message = None, count_default = 0, enable_percent = True):
		global INTERACTIVE

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
		global INTERACTIVE

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

		global INTERACTIVE

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

class base(object):
	verbose = 1

class shader(base):
	__slots__ = ['literals', 'types', 'file', 'nameid', 'size', \
		'parameters', 'type', 'name', 'cmd_mask', \
		'widget_enable_sss',  'id_enable_sss', \
		'widget_sss', 'id_sss', \
		'widget_enable_shadow', 'id_enable_shadow', \
		'widget_shadow', 'id_shadow']

	class parameter(object):
		__slots__ = ['type', 'help', 'default', 'change', 'widget_gui', 'id_gui']

		def __init__(self, type, value, type_name, par_name):
			self.type    = type
			self.default = value
			self.change  = False

			self.help = '%s %s' % (type_name, par_name)
			if (self.default):
				self.help += ' (default: %s)' % self.default

			self.widget_gui = Blender.Draw.Create(value)
			self.id_gui	= get_gui_id(id(self.widget_gui))

		def __deepcopy__(self, memo = {}):

			new_parameter = shader.parameter.__new__(shader.parameter)
			memo[id(self)] = new_parameter

			for attr_name in self.__slots__:
				if (attr_name == 'widget_gui'):
					value = Blender.Draw.Create(getattr(self, attr_name).val)
				elif (attr_name == 'id_gui'):
					value = get_gui_id(id(getattr(new_parameter, 'widget_gui')))
				else:
					value = getattr(self, attr_name)

				setattr(new_parameter, attr_name, value)

			return new_parameter

	def __init__(self, file = None, nameid = None):
		global WINDOWS

		self.literals = enum_type('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
		self.types    = enum_type('surface', 'displacement', 'volume', 'light', 'generic')

		self.size     = 210
		self.cmd_mask = ('""%s" "%s""' if (WINDOWS) else '"%s" "%s"')

		# SSS

		self.widget_enable_sss = Blender.Draw.Create(0)
		self.id_enable_sss = get_gui_id(id(self.widget_enable_sss))

		self.widget_sss = Blender.Draw.Create('diffusefile')
		self.id_sss = get_gui_id(id(self.widget_sss))

		# shadow

		self.widget_enable_shadow = Blender.Draw.Create(1)
		self.id_enable_shadow = get_gui_id(id(self.widget_enable_shadow))

		self.widget_shadow = Blender.Draw.Create('shadowname')
		self.id_shadow = get_gui_id(id(self.widget_shadow))

		self.setup(file, nameid)

	def setup(self, file, nameid):

		self.file   = file
		self.nameid = nameid

		self.parameters = {}
		self.type = None
		self.name = None

		if (file and (not self.parse_file())):
			raise GelatoError, 'Invalid shader'

	def __deepcopy__(self, memo = {}):

		new_shader = shader.__new__(shader)
		memo[id(self)] = new_shader

		for attr_name in self.__slots__:
			if (attr_name in ['widget_enable_sss', 'widget_sss', 'widget_enable_shadow', 'widget_shadow']):
				value = Blender.Draw.Create(getattr(self, attr_name).val)
			elif (attr_name == 'id_enable_sss'):
				value = get_gui_id(id(getattr(new_shader, 'widget_enable_sss')))
			elif (attr_name == 'id_sss'):
				value = get_gui_id(id(getattr(new_shader, 'widget_sss')))
			elif (attr_name == 'id_enable_shadow'):
				value = get_gui_id(id(getattr(new_shader, 'widget_enable_shadow')))
			elif (attr_name == 'id_shadow'):
				value = get_gui_id(id(getattr(new_shader, 'widget_shadow')))
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
		return self.parameters[key].widget_gui.val

	def __setitem__(self, key, value):
		global INTERACTIVE

		par = self.parameters[key]
		par.widget_gui.val = str(value)
		par.change = True

		if (INTERACTIVE):
			Blender.Draw.Redraw(1)

	def get_change(self, key):
		return self.parameters[key].change

	def __str__(self):
		if ((self.type is None) or (not self.name)):
			if (base.verbose > 1):
				print 'Error: null shader'
			return ''

		slist = []
		for name, par in self.parameters.iteritems():

			# skip if no change

			if (not par.change):
				continue

			ty = par.type

			# float

			if (ty is self.literals.float):

				try:
					slist.append('Parameter ("float %s", %s)\n' %
						(name, float(par.widget_gui.val)))
				except ValueError:
					if (base.verbose > 1):
						print 'Error: parameter not valid "%s"' % par.widget_gui.val
					continue

			# string

			elif (ty is self.literals.string):

				slist.append('Parameter ("string %s", "%s")\n' %
					(name, par.widget_gui.val.strip()))

			# color, point, vector, normal

			elif (ty in [self.literals.color, self.literals.point, self.literals.vector, self.literals.normal]):

				val = par.widget_gui.val.strip()
				lpar = val.split(' ')
				l = len(lpar)
				if (l == 1):
					slist.append('Parameter ("%s %s", %s)\n' %
						(self.literals[ty], name, val))
				elif (l == 3):
					slist.append('Parameter ("%s %s", (%s))\n' %
						(self.literals[ty], name, ', '.join(lpar)))
				else:
					if (base.verbose > 1):
						print 'Error: parameter not valid "%s"' % par.widget_gui.val
					continue

			# TODO matrix

			else:
				if (base.verbose > 1):
					print 'Error: unknow parameter "%s"' % name


		ty = self.type

		# Shader: surface, displacement, volume, generic

		if (ty in [self.types.surface, self.types.displacement, self.types.volume, self.types.generic]):
			slist.append('Shader ("%s", "%s")\n' % (self.types[ty], self.name))

		# Shader: light

		elif (ty is self.types.light):
			slist.append('Light ("%s", "%s")\n' % (self.nameid, self.name))

		else:
			if (base.verbose > 1):
				print 'Error: unknow type shader "%s"' % self.types[ty]
			return ''

		return ''.join(slist)

	def default(self):
		for val in self.parameters.itervalues():
			val.widget_gui = Blender.Draw.Create(val.default)
			val.change = False

	def update(self, id):
		for val in self.parameters.itervalues():
			if (val and (val.id_gui == id)):
				val.change = True
				return

	def gui(self, x, y, h, s):
		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		Blender.BGL.glRasterPos2i(x+2, y+h/2-4)

		txt = 'Shader type "%s" name: ' % self.types[self.type]

		Blender.Draw.Text(txt)
		Blender.BGL.glColor3f(1.0, 1.0, 0.8)
		Blender.BGL.glRasterPos2i(x+Blender.Draw.GetStringWidth(txt)+6, y+h/2-4)
		Blender.Draw.Text(self.name)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		y += s
		i = 0
		j = 0

		for name in sorted(self.parameters, key=str.lower, reverse=True):
			par = self.parameters[name]
			ty  = par.type

			# float

			if (ty is self.literals.float):
				par.widget_gui = Blender.Draw.String(name + ': ', par.id_gui, x + j, y,
					self.size, h, par.widget_gui.val, 80, par.help)
				i += 1

			# string

			elif (ty is self.literals.string):
				par.widget_gui = Blender.Draw.String(name + ': ', par.id_gui, x + j, y,
					self.size, h, par.widget_gui.val, 128, par.help)
				i += 1

			# color, point, vector, normal

			elif (ty in [self.literals.color, self.literals.point, self.literals.vector, self.literals.normal]):
				par.widget_gui = Blender.Draw.String(name + ': ', par.id_gui, x + j, y,
					self.size, h, par.widget_gui.val, 256, par.help)
				i += 1
			else:
				if (base.verbose > 1):
					print 'Error: unknow parameter "%s"' % name
				continue

			if (i % 3):
				j += self.size + 10
			else:
				j = 0
				y += s

		if (j == 0):
			y -= s

		return y

	def gui_sss(self, x, y, h, s):
		self.widget_enable_sss = Blender.Draw.Toggle('Enable SSS', self.id_enable_sss, x, y, 100, h,
			self.widget_enable_sss.val, 'Enable SubSurface Scattering')

		if (self.widget_enable_sss.val):
			self.widget_sss = Blender.Draw.String('parameter: ', self.id_sss, x + 110, y, 210, h,
				self.widget_sss.val, 100, 'Name of parameter containing diffuse file from the first SSS pass')

	def gui_shadow(self, x, y, h, s):
		self.widget_enable_shadow = Blender.Draw.Toggle('Enable shadow', self.id_enable_shadow, x, y, 100, h,
			self.widget_enable_shadow.val, 'Enable shadow')

		if (self.widget_enable_shadow.val):
			self.widget_shadow = Blender.Draw.String('parameter: ', self.id_shadow, x + 110, y, 210, h,
				self.widget_shadow.val, 100, 'Name of parameter containing the name of the shadow map')

	def parse_file(self):

		# open file

		cmd = self.cmd_mask % (GSOINFO, self.file)

		try:
			fd = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).stdout
		except:
			if (base.verbose > 0):
				sys.excepthook(*sys.exc_info())
				print 'Error: command "%s"' % cmd
			return False

		# read first line

		line = fd.readline().strip()

		try:
			(type, name) = line.split(' ')
		except ValueError:
			return False

		if (not self.types.has_key(type)):
			if (base.verbose > 1):
				print 'Error: unknow shader type "%s" name "%s"' % (type, name)
			return False

		# shader and name type

		self.type = self.types[type]
		self.name = name

		i = 0
		for line in fd:
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

			if (not self.literals.has_key(elements[0])):
				if (base.verbose > 1):
					print 'Error: unknow parameter type "%s"' % elements
				continue

			par_name = None
			par      = None

			lit = self.literals[elements[0]]

			# float

			if ((lit is self.literals.float) and (l >= 3)):
				par_name = elements[1]
				par      = self.parameter(lit, elements[2], self.literals[lit], par_name)

			# string

			elif ((lit is self.literals.string) and (l >= 3)):
				par_name = elements[1]
				par      = self.parameter(lit, elements[2][1:-1], self.literals[lit], par_name)

			# color, point, vector, normal

			elif ((lit in [self.literals.color, self.literals.point, self.literals.vector, self.literals.normal]) and (l >= 3)):
				val = elements[2]
				try:
					if ((l >= 7) and (elements[2] == '[' and elements[6] == ']')):
						val = '%s %s %s' % (elements[3], elements[4], elements[5])
				except:
					pass

				par_name = elements[1]
				par      = self.parameter(lit, val, self.literals[lit], par_name)

			# TODO matrix

			if ((par_name is None) or (par is None)):
				if (base.verbose > 1):
					print 'Error: unknow parameter "%s"' % elements
					continue

			self.parameters[par_name] = par
			i += 1

		fd.close()

		return True

	def toxml(self, document, root):
		if (not self.file):
			return False

		# file

		(directory, filename) = os.path.split(self.file)

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

			el.appendChild(document.createTextNode(par.widget_gui.val))

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
			fd = search_file(filename, persistents['path_shader'].val)
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
				self.parameters[name].widget_gui = Blender.Draw.Create(attr.firstChild.data.strip())
				self.parameters[name].change     = True

		return True

class gelato_pyg(object):

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
			self.smooth       = False
			self.index_faces  = []
			self.nverts       = []
			self.verts        = []
			self.normals      = []
			self.uvlayers     = {}

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

		self.ZERO = ctypes.c_float(0.0)

		self.EXT_SHADOWMAP = '.sm'
		self.EXT_TEXTURE   = '.tx'
		self.EXT_DIFFUSE   = '.sdb'
		self.EXT_PHOTONMAP = '.sdb'

		self.passes = enum_type('beauty', 'shadows', 'ambient_occlusion', 'photon_map', 'bake_diffuse')

		self.pbar = progress_bar(78)

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
		global materials_assign

		if (not self.format):
			raise GelatoError, 'No output format'

		shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
		if (shader_ambient_occlusion):
			self.file.write('\nAttribute ("string geometryset", "+%s")\n' %
				shader_ambient_occlusion['occlusionname'])

			self.file.write(str(shader_ambient_occlusion))
		else:
			self.file.write('\nAttribute ("string geometryset", "+localocclusion")\n')
			self.file.write('Shader ("surface", "ambocclude", "string occlusionname", "localocclusion")\n')

	def write_ambient_occlusion_pass2(self):
		global materials_assign, lights_assign

		if (not self.format):
			raise GelatoError, 'No output format'

		output = str(self.output_ambient_occlusion_tx)

		self.file.write('\n')

		shader_environment_light = lights_assign[0]['environment_light']
		if (shader_environment_light is not None):
			shader_environment_light['occlusionmap'] = output

			shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
			if (shader_ambient_occlusion is not None):
				shader_environment_light['occlusionname'] = shader_ambient_occlusion['occlusionname']

			self.file.write(str(shader_environment_light))
		else:
			self.file.write('Light ("__envlight_pass2__", "envlight", "string occlusionmap", "%s" )\n' %
				output)

	def write_shader_photon_map_pass1(self):
		self.file.write('\nPushAttributes ()\n')

		shader_shoot_photons = materials_assign[0]['shoot_photons']
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

		shader_caustic_light = lights_assign[0]['caustic_light']
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
		global lights_assign

		if (self.verbose > 0):
			self.file.write('\n## Indirect light\n\n')

		self.file.write('Attribute ("string geometryset", "+indirect")\n')
		self.file.write('Attribute ("int indirect:minsamples", %d)\n' %
			self.indirect_minsamples)

		self.file.write('\n')

		shader_indirect_light = lights_assign[0]['indirect_light']
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

		self.file.write('\nPushTransform ()\n')

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

		self.file.write('PopTransform ()\n')

	def write_distantlight(self, obj, lamp, matrix):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

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

		self.file.write('PopTransform ()\n')

	def write_spotlight(self, obj, lamp, matrix):
		name = obj.name

		self.file.write('\nPushTransform ()\n')

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

		self.file.write('PopTransform ()\n')

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
		cam	= Blender.Camera.Get(obj.getData().name)

		ratio_x = self.context.aspectRatioX()
		ratio_y = self.context.aspectRatioY()
		ratio	= float(ratio_y) / float(ratio_x)

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

		if (cam.type == 'persp'):

			if (ratio_x != ratio_y):
				aspx = self.sizex / self.sizey
				aspy = ratio
				self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
					(-aspx, aspx, -aspy, aspy))

			fac = (self.sizey / self.sizex if (self.sizex > self.sizey) else 1.0)

			fov = math.degrees(2.0 * math.atan2(16.0 * fac, cam.lens))

			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %s)\n' %
				round(fov, self.PRECISION))

		# orthographic camera

		elif (cam.type == 'ortho'):

			aspx = cam.scale / 2.0
			aspy = aspx * self.sizey / self.sizex * ratio

			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
				(-aspx, aspx, -aspy, aspy))

		else:
			raise GelatoError, 'Invalid camera type "%s"' % cam.type

		self.file.write('Attribute ("float pixelaspect", %s)\n' % (1.0 / ratio))

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
		global lights_assign

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

		sd = lights_assign[1].get(lname)
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
		global lights_assign

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

		if (lights_assign[1].has_key(lname) and (lights_assign[1][lname] is not None)):

			sd = copy.deepcopy(lights_assign[1][lname])
			sd.nameid = self.object_name(name)

			self.file.write('\nPushTransform ()\n')

			self.write_move_scale_rotate(mat)

			# shadow

			if (sd.widget_enable_shadow.val):
				self.write_shadow_name(name, sd.widget_shadow.val)

			self.file.write(str(sd))

			self.file.write('PopTransform ()\n')

		else:
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

		# texture files

		textures_color = []
		textures_displacement = []

		list_tex = material.getTextures()

		if (list_tex):
			for mtex in list_tex:

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

			enable_shadergroup = not self.enable_debug_shaders and self.enable_textures and textures_color and (self.current_pass == self.passes.beauty)

			if (enable_shadergroup):
				self.file.write('ShaderGroupBegin ()\n')

			# texture color

			if ((not self.enable_debug_shaders) and self.enable_textures):
				for ftex in textures_color:
					if (self.verbose > 0):
						self.file.write('## Texture color: "%s"\n' % ftex.name)

					self.file.write('Parameter ("string texturename", "%s")\n' % fix_file_name(ftex.filename))
					self.file.write('Parameter ("string wrap", "%s")\n' % self.convert_extend[ftex.extend])
					self.file.write('Shader ("surface", "pretexture")\n')

			# shader surface (FIXME)

			if ((not self.enable_debug_shaders) and (self.verbose > 0)):
				self.file.write('## Material: "%s"\n' % mat_name)

			if (self.enable_shaders and not (self.enable_debug_shaders or (self.current_pass == self.passes.photon_map))):

				if ((not (flags & Blender.Material.Modes.SHADELESS)) and not (bake_diffuse and (self.current_pass == self.passes.bake_diffuse))):

					if (materials_assign[1].has_key(mat_name)):

						sd = copy.deepcopy(materials_assign[1][mat_name])
						if (sd is not None):
							if (bake_diffuse and self.enable_bake_diffuse and (self.current_pass == self.passes.beauty) and sd.widget_enable_sss.val):
								try:
									file_name = self.file_diffuse_name(name)
									sd[sd.widget_sss.val] = file_name
								except:
									if (self.verbose > 0):
										sys.excepthook(*sys.exc_info())

							self.file.write(str(sd))
					else:
						# default plastic
						self.file.write('Shader ("surface", "plastic")\n')

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
		global materials_assign

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

		single_sided = not (self.all_double_sided or (meshes[0].mode & Blender.Mesh.Modes.TWOSIDED))

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

			shader_bake_diffuse = materials_assign[0]['bake_diffuse']
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

			ngeometry  = len(db_mesh[0].db_geometry)

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
		if (not ((self.frame is None) or (self.nframes is None))):
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
		if (not ((self.frame is None) or (self.nframes is None))):
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

		if (not ((self.frame is None) or (self.nframes is None))):
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

		fps = float(self.context.fps)

		try:
			fps /= self.context.fpsBase
		except:
			pass

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
				self.write_device(self.title + ' - ' + self.scene.name, 'iv', self.data_color, self.camera_name)

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

		if (self.enable_sky and
			(self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
			self.write_background_color()

		# ligths key fill rim

		if (self.enable_key_fill_rim and
			(self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
				self.write_key_fill_rim()

		# lights

		if (self.enable_lights and
			(self.current_pass in [self.passes.beauty, self.passes.photon_map, self.passes.bake_diffuse])):
				self.lights()

		# shadow ray traced

		if (self.shadow_ray_traced and
			(self.current_pass in [self.passes.beauty, self.passes.bake_diffuse])):
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

		if (self.enable_debug_shaders and
			(self.current_pass != self.passes.photon_map) and
			gelato_gui.debug_shader is not None):
				self.file.write('\n')
				self.file.write(str(gelato_gui.debug_shader))

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
		global persistents, gelato_gui

		for name, value in persistents.iteritems():
			if (name[0] in ['_', '$']):
				setattr(self, name[1:], value.val)
			else:
				setattr(self, name, value.val)

		# filename

		self.filename = fix_file_name(self.filename)

		# compression

		comp = gelato_gui.menu_format.convert(self.format)[2]

		self.compression = (comp.convert(self.compression) if (comp) else None)

		self.compression_shadow = gelato_gui.menu_compression_tiff.convert(self.compression_shadow)

		# output file name image

		(self.format, self.suffix) = gelato_gui.menu_format.convert(self.format)[0:2]

		# output data

		(self.data_color, self.data_z) = gelato_gui.menu_data.convert(self.data)

		# bucketorder

		self.bucketorder = gelato_gui.menu_bucketorder.convert(self.bucketorder)

		# pixel filter

		self.filter = gelato_gui.menu_filter2.convert(self.filter)

		# units

		self.units_length = gelato_gui.menu_units.convert(self.units_length)

		# stereo cameras

		self.stereo_projection = gelato_gui.menu_stereo_projection.convert(self.stereo_projection)
		self.stereo_shade      = gelato_gui.menu_stereo_shade.convert(self.stereo_shade)

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

		self.frame   = None
		self.nframes = None

		staframe = Blender.Get('staframe')
		curframe = Blender.Get('curframe')
		endframe = Blender.Get('endframe')

		self.mask = '.%%0%dd' % len('%d' % endframe)

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

		# set verbose

		base.verbose = self.verbose

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

				self.nframes = endframe - staframe + 1

				if (self.nframes <= 0):
					raise GelatoError, 'Invalid frame length'

				# all frames

				try:
					for self.frame in xrange(staframe, endframe + 1):
						Blender.Set('curframe', self.frame)

						if (self.verbose > 1):
							print 'Info: exporting frame %d' % self.frame

						self.sequence_pass()
				finally:
					Blender.Set('curframe', curframe)

			else:
				# single frame

				self.sequence_pass()

			# command file

			if (self.nframes or (self.npasses > 1) or self.pass_ambient_occlusion):

				self.frame = None

				try:
					self.file = open(str(self.filename), 'w')
				except IOError:
					raise GelatoError, 'Cannot write file "%s"' % self.filename

				if (self.enable_anim):
					for self.frame in xrange(staframe, endframe + 1):
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

# GUI

class cfggui(object):
	class panel(object):
		__slots__ = ['name', 'reg_name', 'func', 'help', 'id']

		def __init__(self, name, reg_name, func, help):
			self.name     = name
			self.reg_name = reg_name
			self.func     = func
			self.help     = help
			self.id       = 0

	class bake_menu(object):
		__slots__ = ['cookie', 'store', 'food']

		def __init__(self, title = None, options = None,):
			slist = []

			if (title):
				slist.append('%s %%t' % title)

			self.store = {}
			self.food  = {}
			for i, (name, data) in enumerate(options):
				slist.append('|%s %%x%d' % (name, i))
				self.store[i] = data
				self.food[name] = i

			self.cookie = ''.join(slist)

		def convert(self, id):
			return self.store.get(id)

		def val(self, name):
			return self.food.get(name)

	def __init__(self):
		global WINDOWS, materials_assign, lights_assign

		self.x0      = 10	# start cursor x
		self.y0      = 10	# start cursor y
		self.h       = 22	# height button
		self.s       = 30	# step y
		self.m       = 10	# margin button
		self.spd     = 540	# space default button
		self.xoffset = 0	# offset scroll x
		self.yoffset = 0	# offset scroll y
		self.xstep   = 20	# scroll sep x
		self.ystep   = 20	# scroll sep y

		self.color_bg   = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.5325, 0.6936, 0.0])
		self.color_text = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.0, 0.0, 0.0])

		self.color_rect_sw = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.2, 0.2, 0.2])
		self.color_rect    = Blender.BGL.Buffer(Blender.BGL.GL_FLOAT, 3, [0.2392, 0.3098, 1.0])

		self.cmd_mask = ('""%s" "%s""' if (WINDOWS) else '"%s" "%s"&')

		self.active_obj = None
		self.active_mat = None

		self.menu_surface    = None
		self.menu_light      = None
		self.menu_material   = None
		self.menu_lamp       = None
		self.menu_script     = None
		self.menu_postscript = None
		self.menu_prescript  = None

		self.id_enable_header_postscript = None
		self.id_enable_header_prescript  = None
		self.id_enable_world_postscript  = None
		self.id_enable_world_prescript   = None

		self.list_obj_property = [

			# ID			     # persistent	       # property

			['id_obj_excluded',          '_obj_excluded',          'excluded'],
			['id_obj_enable_postscript', '_obj_enable_postscript', 'enable_postscript'],
			['id_obj_enable_prescript',  '_obj_enable_prescript',  'enable_prescript'],

			['id_geo_catmull_clark',     '_geo_catmull_clark',     'catmull_clark'],
			['id_geo_raster_width',      '_geo_raster_width',      'raster_width'],
			['id_geo_bake_diffuse',      '_geo_bake_diffuse',      'bake_diffuse'],
			['id_geo_indirect_light',    '_geo_indirect_light',    'indirect_light'],
			['id_geo_mb_transformation', '_geo_mb_transformation', 'motionblur_transformation'],
			['id_geo_mb_deformation',    '_geo_mb_deformation',    'motionblur_deformation'],
			['id_geo_enable_proxy',      '_geo_enable_proxy',      'enable_proxy'],
			['id_geo_proxy_file',        '_geo_proxy_file',        'proxy_file'],

			['id_lamp_photon_map',       '_lamp_photon_map',       'photon_map'],
		]

		self.list_mat_property = [

			# ID			     # persistent	       # property

			['id_mat_enable_script',     '_mat_enable_script',     'enable_script'],
			['id_mat_enable_postscript', '_mat_enable_postscript', 'enable_postscript'],
			['id_mat_enable_prescript',  '_mat_enable_prescript',  'enable_prescript'],
		]

		for l in [self.list_obj_property, self.list_mat_property]:
			for (id_obj, dummy1, dummy2) in l:
				setattr(self, id_obj, None)

		self.panels = [
			self.panel('Output',         '_panel_output', self.panel_output, 'Panel output data'),
			self.panel('Objects',        '_panel_objects', self.panel_objects, 'Panel objects'),
			self.panel('Geometries',     '_panel_geometries', self.panel_geometries, 'Panel geometries'),
			self.panel('Lights',         '_panel_lights', self.panel_lights, 'Panel lights'),
			self.panel('Textures',       '_panel_textures', self.panel_textures, 'Panel textures'),
			self.panel('Stereo',         '_panel_stereo', self.panel_stereo, 'Panel stereo (anaglyph) rendering'),

			self.panel('Images',         '_panel_images', self.panel_images, 'Panel images'),
			self.panel('Shaders',        '_panel_shaders', self.panel_shaders, 'Panel shaders'),
			self.panel('Ray traced',     '_panel_ray_traced', self.panel_ray_traced, 'Panel ray traced'),
			self.panel('Displacement',   '_panel_displacement', self.panel_displacement, 'Panel displacement'),
			self.panel('Motion Blur',    '_panel_motion_blur', self.panel_motion_blur, 'Panel Motion Blur'),
			self.panel('Depth of Field', '_panel_dof', self.panel_dof, 'Panel depth of field'),

			self.panel('Shadows',        '_panel_shadows', self.panel_shadows, 'Panel select shadows type'),
			self.panel('AO',             '_panel_ambient_occlusion', self.panel_ambient_occlusion, 'Panel ambient occlusion'),
			self.panel('SSS',            '_panel_sss', self.panel_sss, 'Panel SubSurface Scattering'),
			self.panel('Caustics',       '_panel_caustics', self.panel_caustics, 'Panel caustics'),
			self.panel('Indirect Light', '_panel_indirectlight', self.panel_indirect_light, 'Panel indirect light'),
			self.panel('Environment',    '_panel_environment', self.panel_environment, 'Panel environment'),

			self.panel('Pass',           '_panel_pass', self.panel_pass, 'Panel select passes'),
			self.panel('Rerender',       '_panel_rerender', self.panel_rerender, 'Panel select rerender'),
			self.panel('Scripts',        '_panel_scripts', self.panel_scripts, 'Panel scripts'),
		]

		# ambient occlusion shader

		sd = None
		file_name = 'ambocclude.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd)
				self.ambient_occlusion_setup(sd)
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Ambient occlusion is disabled' % file_name

		materials_assign[0]['ambient_occlusion'] = sd

		# shoot photons shader

		sd = None
		file_name = 'shootphotons.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd)
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Shoot photons is disabled' % file_name

		materials_assign[0]['shoot_photons'] = sd

		# envlight shader

		sd = None
		file_name = 'envlight.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__envlight_pass2__')
				self.occlusionmap_setup(sd)
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Environment light is disabled' % file_name

		lights_assign[0]['environment_light'] = sd

		# indirect light shader

		sd = None
		file_name = 'indirectlight.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__indirectlight__')
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Indirect light is disabled' % file_name

		lights_assign[0]['indirect_light'] = sd

		# caustic light shader

		sd = None
		file_name = 'causticlight.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__causticlight__')
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Causticlight is disabled' % file_name

		lights_assign[0]['caustic_light'] = sd

		# bake diffuse shader

		sd = None
		file_name = 'bakediffuse.gso'

		try:
			fd = search_file(file_name, persistents['path_shader'].val)
			if (fd):
				sd = shader(fd)
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Bake diffuse is disabled' % file_name

		materials_assign[0]['bake_diffuse'] = sd

		# debug shaders

		self.debug_shader      = None
		self.menu_debug_shader = None

		list_sd = []
		for name in ['shownormals', 'showfacing', 'showst', 'showuv', 'showdudv', 'showgrids', 'raygoggles']:
			fd = search_file(name + '.gso', persistents['path_shader'].val)
			if (fd):
				try:
					sd = shader(fd)

					# only surface shader

					if (sd.type is sd.types.surface):
						list_sd.append([name, sd])
				except:
					sys.excepthook(*sys.exc_info())
					print 'Error: shader "%s" not found.' % name

		if (len(list_sd) > 0):
			self.menu_debug_shader = self.bake_menu('Debug shaders', list_sd)

		# avanable shaders

		self.available_shader = find_files('*.gso', persistents['path_shader'].val)
		if (self.available_shader):
			list_surface = []
			list_light   = []
			for name in sorted(self.available_shader):
				fd = os.path.join(self.available_shader[name], name)
				try:
					sd = shader(fd)

					ty = sd.type

					if (ty is None):
						continue

					# surface, generic

					elif (ty in [sd.types.surface, sd.types.generic]):
						list_surface.append([name[:-4], sd])

					# light

					elif (ty is sd.types.light):
						list_light.append([name[:-4], sd])
				except:
					sys.excepthook(*sys.exc_info())
					print 'Error: shader "%s" not found.' % name

			if (len(list_surface) > 0):
				self.menu_surface = self.bake_menu('Shaders', list_surface)

			if (len(list_light) > 0):
				self.menu_light = self.bake_menu('Shaders', list_light)

		# compression

		self.menu_compression_tiff = self.bake_menu('TIFF compression', [
			['None', 'none'],
			['ZIP',  'zip'],
			['LZW',  'lzw'],
		])

		self.menu_compression_openexr = self.bake_menu('OpenEXR compression', [
			['None',  'none'],
			['ZIP',   'zip'],
			['ZIPS',  'zips'],
			['PIZ',   'piz'],
			['PXR24', 'pxr24'],
		])

		# formats

		self.menu_format = self.bake_menu('Output format', [
			['Null',    [None,	None,    None, '']],
			['TIFF',    ['tiff',	'.tif',  self.menu_compression_tiff,    'TIFF compression']],
			['OpenEXR', ['OpenEXR', '.exr',  self.menu_compression_openexr, 'OpenEXR compression']],
			['PNG',     ['png',	'.png',  None, '']],
			['JPEG',    ['jpg',	'.jpg',  None, '']],
			['TARGA',   ['targa',	'.tga',  None, '']],
			['PPM',     ['ppm',	'.ppm',  None, '']],
			['SGI',     ['DevIL',	'.sgi',  None, '']],
			['BMP',     ['DevIL',	'.bmp',  None, '']],
			['PCX',     ['DevIL',	'.pcx',  None, '']],
			['DDS',     ['DevIL',	'.dds',  None, '']],
			['RAW',     ['DevIL',	'.raw',  None, '']],
			['IFF',     ['iff',	'.iff',  None, '']],
		])

		self.val_format_null	= self.menu_format.val('Null')
		self.val_format_openEXR = self.menu_format.val('OpenEXR')

		# data

		self.menu_data = self.bake_menu('Output data', [
			['RGB',		['rgb',  None]],
			['RGBA',	['rgba', None]],
			['Z',		['z',    None]],
			['RGB + Z',	['rgb',  'z']],
			['RGBA + Z',	['rgba', 'z']],
			['AvgZ',	['avgz', None]],
			['VolZ',	['volz', None]],
		])

		self.val_data_z = self.menu_data.val('Z')

		# bucket orders

		self.menu_bucketorder = self.bake_menu('Bucket order', [
			['Horizontal', 'horizontal'],
			['Vertical',   'vertical'],
			['Spiral',     'spiral'],
		])

		# filters

		filter = [
			['Gaussian',		'gaussian'],
			['Box',			'box'],
			['Triangle',		'triangle'],
			['Catmull-Rom',		'catmull-rom'],
			['Sinc',		'sinc'],
			['Blackman-Harris',	'blackman-harris'],
			['Mitchell',		'mitchell'],
			['B-Spline',		'b-spline'],
		]

		self.menu_filter1 = self.bake_menu('Pixel filter', filter)

		filter.extend([
			['Min',		'min'],
			['Max',		'max'],
			['Average',	'average'],
		])

		self.menu_filter2 = self.bake_menu('Pixel filter', filter)

		self.val_filter_min = self.menu_filter2.val('Min')

		# files extensions

		self.menu_files_extensions = self.bake_menu('Files extensions', [
			['file.$FRAME.ext', 0],
			['file.ext.$FRAME', 1],
		])

		# units

		self.menu_units = self.bake_menu('Units', [
			['None',       None],
			['Millimeter', 'mm'],
			['Centimeter', 'cm'],
			['Meter',      'm'],
			['Kilometer',  'km'],
			['Inch',       'in'],
			['Foot',       'ft'],
			['Mile',       'mi'],
		])

		# stereo cameras

		self.menu_stereo_projection = self.bake_menu('Projection', [
			['Off-axis', 'off-axis'],
			['Parallel', 'parallel'],
			['Toe-in',   'toe-in'],
		])

		self.menu_stereo_shade = self.bake_menu('Shade', [
			['Left',   'left'],
			['Center', 'center'],
			['Right',  'right'],
		])

		self.home()
		self.reset_id()

	def home(self):
		self.x = self.x0 + self.xoffset
		self.y = self.y0 + self.yoffset

	def home_reset(self):
		self.xoffset = 0
		self.yoffset = 0

	def home_down(self):
		self.yoffset += self.ystep
		if (self.yoffset > 0):
			self.yoffset = 0

	def home_up(self):
		self.yoffset -= self.ystep

	def home_left(self):
		self.xoffset -= self.xstep

	def home_right(self):
		self.xoffset += self.xstep
		if (self.xoffset > 0):
			self.xoffset = 0

	def inc_x(self, i = 0):
		self.x += i

	def inc_y(self, i = 0):
		self.y += i

	def line_feed(self, gap = True):
		self.x = self.x0 + self.xoffset
		self.inc_y(self.s if gap else self.h)

	def blank(self, x = 0):
		self.inc_x(x + self.m)

	def reset_id(self):
		self.id_buttons = dict()

	def get_id(self, global_id, func = None):
		id = get_gui_id(global_id)
		self.id_buttons[id] = func
		return id

	def draw_rect(self, x, y, w, h, gap = True):
		Blender.BGL.glRecti(self.x + x, self.y + y, self.x + x + w, self.y + y + h)
		if (gap):
			self.inc_x(w + self.m)

	def draw_text(self, color, str, size, x = 0, y = 0):
		Blender.BGL.glColor3fv(color)
		Blender.BGL.glRasterPos2i(self.x + x, self.y + y)
		Blender.Draw.Text(str)
		self.inc_x(size + self.m)

	def draw_string(self, s, size, length, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		persistents[name] = Blender.Draw.String(s, rid, self.x, self.y, size, self.h,
			persistents[name].val, length, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw_number(self, s, size, min, max, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		persistents[name] = Blender.Draw.Number(s, rid, self.x, self.y, size, self.h,
			persistents[name].val, min, max, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw_slider(self, s, size, min, max, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		persistents[name] = Blender.Draw.Slider(s, rid, self.x, self.y, size, self.h,
			persistents[name].val, min, max, 0, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw_button(self, s, size, func, help = '', sep = None):
		rid = self.get_id(id(func), func)
		Blender.Draw.PushButton(s, rid, self.x, self.y, size, self.h, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw_toggle(self, s, size, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		persistents[name] = Blender.Draw.Toggle(s, rid, self.x, self.y, size, self.h,
			persistents[name].val, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw_menu(self, bake, size, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		persistents[name] = Blender.Draw.Menu(bake.cookie, rid, self.x, self.y, size, self.h,
			persistents[name].val, help)
		self.inc_x(size + (self.m if (sep is None) else sep))
		return rid

	def draw(self):
		self.home()
		self.reset_id()

		Blender.BGL.glClearColor(self.color_bg[0], self.color_bg[1], self.color_bg[2], 1.0)
		Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)

		self.panel_common()
		self.line_feed()
		self.panel_select()

	@staticmethod
	def ambient_occlusion_setup(sd):
		sd['occlusionname'] = 'localocclusion'

	@staticmethod
	def occlusionmap_setup(sd):
		sd['occlusionmap'] = '$FILE_PASS1'

	def handle_event(self, evt, val):
		global persistents

		if ((not val) and (evt in [Blender.Draw.LEFTMOUSE, Blender.Draw.MIDDLEMOUSE, Blender.Draw.RIGHTMOUSE])):
			Blender.Draw.Redraw(1)
			return

		if (evt in [Blender.Draw.ESCKEY, Blender.Draw.QKEY]):
			ret = Blender.Draw.PupMenu('OK?%t|Exit Blender Gelato%x1')
			if (ret == 1):
				config_save()
				Blender.Draw.Exit()
			return

		if (evt == Blender.Draw.HOMEKEY):
			self.home_reset()
			Blender.Draw.Redraw(1)
			return

		if (evt in [Blender.Draw.WHEELDOWNMOUSE, Blender.Draw.DOWNARROWKEY]):
			self.home_down()
			Blender.Draw.Redraw(1)
			return

		if (evt in [Blender.Draw.WHEELUPMOUSE, Blender.Draw.UPARROWKEY]):
			self.home_up()
			Blender.Draw.Redraw(1)
			return

		if (evt == Blender.Draw.LEFTARROWKEY):
			self.home_left()
			Blender.Draw.Redraw(1)
			return

		if (evt == Blender.Draw.RIGHTARROWKEY):
			self.home_right()
			Blender.Draw.Redraw(1)
			return

	def handle_button_event(self, evt):
		global persistents, materials_assign, lights_assign

		if (self.id_buttons.has_key(evt)):
			func = self.id_buttons[evt]
			if (func):
				func(evt)

		# active object

		if (self.active_obj):
			for (id_obj, name, property) in self.list_obj_property:
				if (evt == getattr(self, id_obj)):
					value = persistents[name].val
					property_set(self.active_obj, property, value)

					if ((id_obj == 'id_obj_enable_prescript') and not value):
						property_set(self.active_obj, 'prescript', '')
					elif ((id_obj == 'id_obj_enable_postscript') and not value):
						property_set(self.active_obj, 'postscript', '')

					break

		# active material

		if (self.active_mat):
			for (id_mat, name, property) in self.list_mat_property:
				if (evt == getattr(self, id_mat)):
					value = persistents[name].val
					property_set(self.active_mat, property, value)

					if ((id_mat == 'id_mat_enable_script') and not value):
						property_set(self.active_mat, 'script', '')
					elif ((id_mat == 'id_mat_enable_prescript') and not value):
						property_set(self.active_mat, 'prescript', '')
					elif ((id_mat == 'id_mat_enable_postscript') and not value):
						property_set(self.active_mat, 'postscript', '')

					break

		# scripts

		if ((evt == self.id_enable_header_postscript) and not persistents['enable_header_postscript'].val):
			persistents['header_postscript'] = Blender.Draw.Create('')
		elif ((evt == self.id_enable_header_prescript) and not persistents['enable_header_prescript'].val):
			persistents['header_prescript'] = Blender.Draw.Create('')
		elif ((evt == self.id_enable_world_postscript) and not persistents['enable_world_postscript'].val):
			persistents['world_postscript'] = Blender.Draw.Create('')
		elif ((evt == self.id_enable_world_prescript) and not persistents['enable_world_prescript'].val):
			persistents['world_prescript'] = Blender.Draw.Create('')

		# passes

		if (persistents['format'].val == self.val_format_null):
			persistents['enable_viewer'].val = 1

		if (persistents['enable_dynamic'].val or persistents['shadow_ray_traced'].val):
			persistents['pass_shadows'].val = 0

		if (not persistents['enable_ambient_occlusion'].val):
			persistents['pass_ambient_occlusion'].val = 0

		if (not persistents['enable_caustics'].val):
			persistents['pass_photon_maps'].val = 0

		if (not persistents['enable_bake_diffuse'].val):
			persistents['pass_bake_diffuse'].val = 0

		if (not (persistents['pass_beauty'].val or
			persistents['pass_shadows'].val or
			persistents['pass_ambient_occlusion'].val or
			persistents['pass_photon_maps'].val or
			persistents['pass_bake_diffuse'].val)):
				persistents['pass_beauty'].val = 1

		# filters

		if ((persistents['data'].val < self.val_data_z) and
			(persistents['filter'].val >= self.val_filter_min)):
				persistents['filter'].val = 0 # Gaussian

		# materials

		for sd in materials_assign[0].itervalues():
			if (sd is not None):
				sd.update(evt)

		if (self.menu_material):
			material_name = self.menu_material.convert(persistents['_select_material'].val)
			if (materials_assign[1].has_key(material_name) and (materials_assign[1][material_name] is not None)):
				materials_assign[1][material_name].update(evt)

		if ((persistents['_enable_debug_shaders'].val) and (self.debug_shader is not None)):
			self.debug_shader.update(evt)

		# lights

		for sd in lights_assign[0].itervalues():
			if (sd is not None):
				sd.update(evt)

		if (self.menu_lamp):
			lamp_name = self.menu_lamp.convert(persistents['_select_lamp'].val)
			if (lights_assign[1].has_key(lamp_name) and (lights_assign[1][lamp_name] is not None)):
				lights_assign[1][lamp_name].update(evt)

		# config save

		config_save()

		# redraw

		Blender.Draw.Redraw(1)

	def cb_exit(self, id):
		self.handle_event(Blender.Draw.ESCKEY, 0)

	def cb_default(self, id):
		ret = Blender.Draw.PupMenu('All items to default values ?%t|no%x1|yes%x2')
		if (ret != 2):
			return
		default_values()

	def cb_save(self, id):
		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

		except GelatoError, strerror:

			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_render(self, id):
		global GELATO, persistents

		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

			# run gelato

			filename = persistents['filename'].val

			if (os.path.isfile(filename)):

				pid = subprocess.Popen([GELATO, filename]).pid

				print 'Info: run Gelato pid=%s' % pid

			else:
				raise GelatoError, 'No such file: `%s\'' % filename

		except GelatoError, strerror:

			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_menu_header_postscript(self, id):
		global persistents

		if (self.menu_postscript):
			persistents['header_postscript'] = Blender.Draw.Create(self.menu_postscript.convert(persistents['_select_postscript'].val))

	def cb_menu_header_prescript(self, id):
		global persistents

		if (self.menu_prescript):
			persistents['header_prescript'] = Blender.Draw.Create(self.menu_prescript.convert(persistents['_select_prescript'].val))

	def cb_menu_world_postscript(self, id):
		global persistents

		if (self.menu_postscript):
			persistents['world_postscript'] = Blender.Draw.Create(self.menu_postscript.convert(persistents['_select_postscript'].val))

	def cb_menu_world_prescript(self, id):
		global persistents

		if (self.menu_prescript):
			persistents['world_prescript'] = Blender.Draw.Create(self.menu_prescript.convert(persistents['_select_prescript'].val))

	def cb_menu_obj_prescript(self, id):
		global persistents

		if (self.active_obj and self.menu_prescript):
			property_set(self.active_obj, 'prescript', self.menu_prescript.convert(persistents['_select_prescript'].val))

	def cb_menu_obj_postscript(self, id):
		global persistents

		if (self.active_obj and self.menu_postscript):
			property_set(self.active_obj, 'postscript', self.menu_postscript.convert(persistents['_select_postscript'].val))

	def cb_menu_mat_script(self, id):
		global persistents

		if (self.active_mat and self.menu_script):
			property_set(self.active_mat, 'script', self.menu_script.convert(persistents['_select_script'].val))

	def cb_menu_mat_prescript(self, id):
		global persistents

		if (self.active_mat and self.menu_prescript):
			property_set(self.active_mat, 'prescript', self.menu_prescript.convert(persistents['_select_prescript'].val))

	def cb_menu_mat_postscript(self, id):
		global persistents

		if (self.active_mat and self.menu_postscript):
			property_set(self.active_mat, 'postscript', self.menu_postscript.convert(persistents['_select_postscript'].val))

	def cb_assign_material(self, id):
		global persistents, materials_assign

		material_name = self.menu_material.convert(persistents['_select_material'].val)
		sd = self.menu_surface.convert(persistents['_select_surface'].val)

		if (sd is not None):
			# copy object no reference
			materials_assign[1][material_name] = copy.deepcopy(sd)

	def cb_assign_light(self, id):
		global persistents, lights_assign

		lamp_name = self.menu_lamp.convert(persistents['_select_lamp'].val)
		sd = self.menu_light.convert(persistents['_select_light'].val)

		if (sd is not None):
			# copy object no reference
			lights_assign[1][lamp_name] = copy.deepcopy(sd)

	def cb_remove_material(self, id):
		global persistents, materials_assign

		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		try:
			material_name = self.menu_material.convert(persistents['_select_material'].val)
			del materials_assign[1][material_name]
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_remove_light(self, id):
		global persistents, lights_assign

		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		try:
			lamp_name = self.menu_lamp.convert(persistents['_select_lamp'].val)
			del lights_assign[1][lamp_name]
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())


	def cb_menu_surface(self, id):
#		ret = Blender.Draw.PupMenu('Link shader ?%t|no%x1|yes%x2')
#		if (ret != 2):
#			return
		self.cb_assign_material(id)

	def cb_menu_light(self, id):
#		ret = Blender.Draw.PupMenu('Link shader ?%t|no%x1|yes%x2')
#		if (ret != 2):
#			return
		self.cb_assign_light(id)

	def cb_material_default(self, id):
		global persistents, materials_assign

		material_name = self.menu_material.convert(persistents['_select_material'].val)
		try:
			materials_assign[1][material_name].default()
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_light_default(self, id):
		global persistents, lights_assign

		lamp_name = self.menu_lamp.convert(persistents['_select_lamp'].val)
		try:
			lights_assign[1][lamp_name].default()
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_debug_shader(self, id):
		global persistents

		sd = self.menu_debug_shader.convert(persistents['_select_debug_shader'].val)
		if (sd is not None):
			if ((self.debug_shader is not None) and (self.debug_shader is sd)):
				return
			self.debug_shader = sd

	def cb_ambient_occlusion_default(self, id):
		global materials_assign

		shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
		shader_ambient_occlusion.default()
		self.ambient_occlusion_setup(shader_ambient_occlusion)

	def cb_shoot_photons_default(self, id):
		global materials_assign

		shader_shoot_photons = materials_assign[0]['shoot_photons']
		shader_shoot_photons.default()

	def cb_shader_envlight_default(self, id):
		global lights_assign

		shader_environment_light = lights_assign[0]['environment_light']
		shader_environment_light.default()
		self.occlusionmap_setup(shader_environment_light)

	def cb_shader_indirect_light_default(self, id):
		global lights_assign

		lights_assign[0]['indirect_light'].default()

	def cb_shader_caustic_light_default(self, id):
		global lights_assign

		lights_assign[0]['caustic_light'].default()

	def cb_shader_bake_diffuse_default(self, id):
		global materials_assign

		materials_assign[0]['bake_diffuse'].default()

	def cb_refresh_active_object(self, id):
		self.active_obj = selected_object()

	def cb_deleye_all_properties(self, id):
		ret = Blender.Draw.PupMenu('Are You Sure ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		for data in [Blender.Object.Get(), Blender.Material.Get()]:
			for obj in data:
				if (obj.properties.has_key('gelato')):
					del obj.properties['gelato']

	def cb_shadows(self, id):
		if (id != self.id_shadow_maps):
			persistents['shadow_maps'].val = 0
		if (id != self.id_shadow_woo):
			persistents['shadow_woo'].val = 0
		if (id != self.id_shadow_raytraced):
			persistents['shadow_ray_traced'].val = 0

	def cb_panel(self, id):
		for pan in self.panels:
			if (pan.id != id):
				persistents[pan.reg_name].val = 0

		if (persistents['_panel_objects'].val or
			persistents['_panel_geometries'].val or
			persistents['_panel_lights'].val):
				self.cb_refresh_active_object(0)

	def cb_select(self, name):
		global persistents

		persistents['filename'].val = os.path.abspath(name)

	def cb_errorselect(self, name):
		global persistents

		persistents['error_filename'].val = os.path.abspath(name)

	def cb_proxyselect(self, name):
		global persistents

		if (self.active_obj):
			property_set(self.active_obj, 'proxy_file', os.path.abspath(name))

	def cb_filename(self, id):
		global persistents

		Blender.Window.FileSelector(self.cb_select, '.pyg', persistents['filename'].val)

	def cb_error_filename(self, id):
		global persistents

		Blender.Window.FileSelector(self.cb_errorselect, '.txt', persistents['error_filename'].val)

	def cb_proxy_filename(self, id):
		global persistents

		Blender.Window.FileSelector(self.cb_proxyselect, '.pyg', persistents['_geo_proxy_file'].val)

	def panel_common(self):
		global persistents

		self.draw_text(self.color_text, 'Blender Gelato v' + __version__, 130, 2, 6)

		self.draw_button('Save', 70,
			self.cb_save, 'Save pyg file')

		self.draw_button('Render', 80,
			self.cb_render, 'Save and render pyg file')

		self.blank(170)

		self.draw_button('Default', 80, self.cb_default,
			'Set all items to default values')

		self.draw_button('Exit', 70, self.cb_exit,
			'Exit Python script')

	def panel_select(self):
		global persistents

		for pan in self.panels:
			if (persistents[pan.reg_name].val):
				func = pan.func
				break
		else:
			persistents[self.panels[0].reg_name].val = 1
			func = self.panels[0].func

		for i, pan in enumerate(self.panels):
			pan.id = self.draw_toggle(pan.name, 100, pan.reg_name, self.cb_panel, pan.help)

			if ((i != 19) and (i % 6) == 5):
				self.line_feed()

		self.line_feed()

		Blender.BGL.glColor3fv(self.color_rect_sw)
		self.draw_rect(2, 2, 650, 11, False)
		Blender.BGL.glColor3fv(self.color_rect)
		self.draw_rect(0, 4, 650, 10)

		self.line_feed()

		if (func):
			func()

	def panel_output(self):
		global persistents

		self.draw_toggle('Viewer', 100, 'enable_viewer',
			help = 'Enable window viewer')

		self.draw_toggle('Split', 100, 'enable_split',
			help = 'Split out objects into separate files')

		self.draw_toggle('Binary', 100, 'enable_binary',
			help = 'Enable binary file')

		self.draw_toggle('Relative paths', 100, 'enable_relative_paths',
			help = 'Enable relative paths')

		self.draw_toggle('Pack config', 100, '$pack_config',
			help = 'Enable pack config file (%s)' % output_filename_xml())

		self.line_feed()

		self.draw_text(self.color_text, 'Maximum threads ', 100, 2, 6)

		self.draw_toggle('Auto', 100, 'enable_auto_threads',
			help = 'Auto detect')

		if (not persistents['enable_auto_threads'].val):
			self.draw_number('Threads ', 100, 1, 256, 'limits_threads',
				help = 'Sets the maximum number of parallel execution threads')

		self.line_feed()

		self.draw_text(self.color_text, 'Bucket size', 100, 2, 6)

		l = 105
		v_min = 1
		v_max = 1024

		self.draw_number('X: ', l, v_min, v_max, 'bucketsize_x',
			help = 'Bucket size of pixel rectangles X', sep = 0)

		self.draw_number('Y: ', l, v_min, v_max, 'bucketsize_y',
			help = 'Bucket size of pixel rectangles Y')

		self.draw_menu(self.menu_bucketorder, 100, 'bucketorder',
			help = 'Render bucket order')

		self.line_feed()

		self.draw_toggle('Anim', 100, 'enable_anim',
			help = 'Enable sequence render')

		if (persistents['enable_anim'].val):
			self.draw_menu(self.menu_files_extensions, 120, 'files_extensions',
				help = 'Templates files extensions')

		self.line_feed()

		self.draw_toggle('Preview', 100, 'enable_preview',
			help = 'Enable preview')

		if (persistents['enable_preview'].val):
			self.draw_slider('Preview quality: ', 320, 0.0, 1.0, 'preview_quality',
				help = 'Preview quality')

		self.line_feed()

		self.draw_toggle('Enable error', 100, 'enable_error',
			help = 'Enable error file')

		if (persistents['enable_error'].val):
			self.draw_button('Error file:', 100, self.cb_error_filename,
				'Select log file (default: ">>gelato_log.txt")', 0)

			self.draw_string('', 440, 200, 'error_filename',
				help = 'Error log file')

		self.line_feed()

		self.draw_button('Filename:', 100, self.cb_filename,
			'Select file name', 0)

		self.draw_string('', 550, 200, 'filename',
			help = 'File name')

		self.line_feed()

		self.draw_string('Path inputs: ', 650, 250, 'path_inputs',
			help = 'Search path for scene files')

		self.line_feed()

		self.draw_string('Path textures: ', 650, 250, 'path_texture',
			help = 'Search path for texture files')

		self.line_feed()

		self.draw_string('Path shader: ', 650, 250, 'path_shader',
			help = 'Search path for compiled shaders')

		self.line_feed()

		self.draw_string('Path imageio: ', 650, 250, 'path_imageio',
			help = 'Search path for image format input/output DSO\'s')

		self.line_feed()

		self.draw_string('Path generator: ', 650, 250, 'path_generator',
			help = 'Search path for generators DSO\'s')

	def panel_images(self):
		global persistents

		self.draw_menu(self.menu_data, 105, 'data',
			help = 'Output data')

		self.draw_menu(self.menu_format, 105, 'format',
			help = 'Output format')

		(comp, comp_help) = self.menu_format.convert(persistents['format'].val)[2:4]
		if (comp):
			self.draw_menu(comp, 105, 'compression',
				help = comp_help)

		self.line_feed()

		self.draw_number('Gain: ', 105, 0.0, 16.0, 'gain',
			help = 'Image gain')

		self.draw_number('Gamma: ', 105, 0.0, 16.0, 'gamma',
			help = 'Image gamma')

		self.line_feed()

		self.draw_text(self.color_text, 'Spatial antialiasing', 105, 2, 6)

		l = 110
		v_min = 1
		v_max = 32

		self.draw_number('X: ', l, v_min, v_max, 'antialiasing_x',
			help = 'Spatial antialiasing X', sep = 0)

		self.draw_number('Y: ', l, v_min, v_max, 'antialiasing_y',
			help = 'Spatial antialiasing Y')

		self.line_feed()

		self.draw_text(self.color_text, 'Pixel filter width', 105, 2, 6)

		l = 110
		v_min = 0.0
		v_max = 32.0

		self.draw_number('X: ', l, v_min, v_max, 'filterwidth_x',
			help = 'Pixel filter width X', sep = 0)

		self.draw_number('Y: ', l, v_min, v_max, 'filterwidth_y',
			help = 'Pixel filter width Y')

		menu_filter = (self.menu_filter1 if (persistents['data'].val < self.val_data_z) else self.menu_filter2)

		self.draw_menu(menu_filter, 130, 'filter',
			help = 'Pixel filter')

		self.line_feed()

		v = persistents['format'].val
		if ((v != self.val_format_null) and (v != self.val_format_openEXR)):

			self.draw_text(self.color_text, 'Quantize', 50, 2, 6)

			l = 120
			l_max = 20

			self.draw_string('zero: ', l, l_max, 'quantize_zero',
				help = 'Quantization parameter zero', sep = 0)

			self.draw_string('one: ', l, l_max, 'quantize_one',
				help = 'Quantization parameter one', sep = 0)

			self.draw_string('min: ', l, l_max, 'quantize_min',
				help = 'Quantization parameter min', sep = 0)

			self.draw_string('max: ', l, l_max, 'quantize_max',
				help = 'Quantization parameter max')

			self.draw_number('Dither: ', 100, 0.0, 10.0, 'dither',
				help = 'Dither amplitude')

	def panel_pass(self):
		global persistents

		self.draw_toggle('Beauty', 130, 'pass_beauty',
			help = 'Enable beauty pass')

		if ((not persistents['enable_dynamic'].val) and
			(persistents['shadow_maps'].val or persistents['shadow_woo'].val)):
				self.line_feed(False)
				self.draw_toggle('Shadows', 130, 'pass_shadows',
					help = 'Enable shadows pass')

		if (persistents['enable_ambient_occlusion'].val):
			self.line_feed(False)
			self.draw_toggle('Ambient Occlusion', 130, 'pass_ambient_occlusion',
				help = 'Enable ambient occlusion pass')

		if (persistents['enable_caustics'].val):
			self.line_feed(False)
			self.draw_toggle('Photon map', 130, 'pass_photon_maps',
				help = 'Enable photon map pass')

		if (persistents['enable_bake_diffuse'].val):
			self.line_feed(False)
			self.draw_toggle('Bake diffuse', 130, 'pass_bake_diffuse',
				help = 'Enable bake diffuse pass')

	def panel_rerender(self):
		self.draw_toggle('Enable', 100, 'enable_rerender',
			help = 'Enable the renderer in "re-render" mode')

		if (persistents['enable_rerender'].val):
			self.draw_string('Rerender memory: ', 210, 30, 'rerender_memory',
				help = 'Size of re-render caches in KB')

	def panel_objects(self):
		global persistents

		self.draw_button('Delete all properties', 130,
			self.cb_deleye_all_properties, 'Delete all object\'s properties')

		self.line_feed()

		self.draw_button('Refresh object', 130,
			self.cb_refresh_active_object, 'Refresh active object')

		if (not self.active_obj):

			self.draw_text(self.color_text, 'No object selected', 50, 2, 6)
		else:

			excluded = property_boolean_get(self.active_obj, 'excluded')

			self.draw_text(self.color_text, 'Object: "%s"' % self.active_obj.name, 50, 2, 6)

			self.line_feed()

			persistents['_obj_excluded'] = Blender.Draw.Create(excluded)
			self.id_obj_excluded = self.draw_toggle('Excluded', 130, '_obj_excluded',
				help = 'Excluded object exports')

			if (not excluded):
				if (persistents['enable_scripts'].val):

					l = 100

					texts = Blender.Text.Get()

					self.line_feed()

					enable_postscript = property_boolean_get(self.active_obj, 'enable_postscript')
					persistents['_obj_enable_postscript'] = Blender.Draw.Create(enable_postscript)
					self.id_obj_enable_postscript = self.draw_toggle('Object post-script', 130, '_obj_enable_postscript',
						help = 'Enable post-script')

					if (enable_postscript):

						script = property_string_get(self.active_obj, 'postscript')

						if (script):
							self.draw_text(self.color_text, script, l, 2, 6)
						elif (texts):
							self.menu_postscript = self.bake_menu('Load post-script from text',
								[[t.name, t.name] for t in texts])

							self.draw_menu(self.menu_postscript, l, '_select_postscript',
								self.cb_menu_obj_postscript, 'Select post-script')

					self.line_feed()

					enable_prescript  = property_boolean_get(self.active_obj, 'enable_prescript')
					persistents['_obj_enable_prescript'] = Blender.Draw.Create(enable_prescript)
					self.id_obj_enable_prescript = self.draw_toggle('Object pre-script', 130, '_obj_enable_prescript',
						help = 'Enable pre-script')

					if (enable_prescript):

						script = property_string_get(self.active_obj, 'prescript')

						if (script):
							self.draw_text(self.color_text, script, l, 2, 6)
						elif (texts):
							self.menu_prescript = self.bake_menu('Load pre-script from text',
								[[t.name, t.name] for t in texts])

							self.draw_menu(self.menu_prescript, l, '_select_prescript',
								self.cb_menu_obj_prescript, 'Select pre-script')

	def panel_geometries(self):
		global persistents

		obj_ok       = False
		excluded     = False
		enable_proxy = False

		if (self.active_obj):

			obj_ok = self.active_obj.type in ['Mesh', 'Surf']

			if (obj_ok):

				excluded     = property_boolean_get(self.active_obj, 'excluded')
				enable_proxy = property_boolean_get(self.active_obj, 'enable_proxy')

				if (not excluded and enable_proxy):
					self.draw_text(self.color_text, 'Proxy use only the first material assigned to the object', 130, 2, 6)
					self.line_feed()

		self.draw_toggle('All double sided', 130, 'all_double_sided',
			help = 'Enable all double sided faces')

		self.draw_toggle('Dupli verts', 130, 'enable_dupli_verts',
			help = 'Enable Dupli verts')

		self.draw_toggle('Vextex color', 130, 'enable_vextex_color',
			help = 'Enable vextex color')

		self.draw_toggle('Halos', 130, 'enable_halos',
			help = 'Enable halos (points)')

		self.line_feed()

		self.draw_button('Refresh object', 130,
			self.cb_refresh_active_object, 'Refresh active object')

		if (not obj_ok):

			self.draw_text(self.color_text, 'No geometry selected', 50, 2, 6)
		else:
			excluded = property_boolean_get(self.active_obj, 'excluded')

			self.draw_text(self.color_text, 'Geometry: "%s"%s' %
				(self.active_obj.name, (' (excluded)' if excluded else '')), 50, 2, 6)

			if (not excluded):

				catmull_clark  = property_boolean_get(self.active_obj, 'catmull_clark')
				raster_width   = property_boolean_get(self.active_obj, 'raster_width')
				bake_diffuse   = property_boolean_get(self.active_obj, 'bake_diffuse')
				indirect_light = property_boolean_get(self.active_obj, 'indirect_light', True)

				self.line_feed()

				persistents['_geo_catmull_clark'] = Blender.Draw.Create(catmull_clark)
				self.id_geo_catmull_clark = self.draw_toggle('Catmull Clark', 130, '_geo_catmull_clark',
					help = 'Enable catmull-clark property')
				
				if (persistents['enable_halos'].val):
					
					persistents['_geo_raster_width'] = Blender.Draw.Create(raster_width)
					self.id_geo_raster_width = self.draw_toggle('Halo raster width', 130, '_geo_raster_width',
						help = 'Enable raster width (diameter of the point)')

				if (persistents['enable_bake_diffuse'].val):

					persistents['_geo_bake_diffuse'] = Blender.Draw.Create(bake_diffuse)
					self.id_geo_bake_diffuse = self.draw_toggle('Bake diffuse', 130, '_geo_bake_diffuse',
						help = 'Enable bake diffuse property')

				if (persistents['enable_indirect_light'].val):

					persistents['_geo_indirect_light'] = Blender.Draw.Create(indirect_light)
					self.id_geo_indirect_light = self.draw_toggle('Enable indirect', 130, '_geo_indirect_light',
						help = 'Enable indirect light')

				if (persistents['enable_motion_blur'].val):

					motionblur_transformation = property_boolean_get(self.active_obj, 'motionblur_transformation', True)
					motionblur_deformation    = property_boolean_get(self.active_obj, 'motionblur_deformation')

					self.line_feed()

					persistents['_geo_mb_transformation'] = Blender.Draw.Create(motionblur_transformation)
					self.id_geo_mb_transformation = self.draw_toggle('Motion blur transformation', 160, '_geo_mb_transformation',
						help = 'Enable motion blur transformation')

					persistents['_geo_mb_deformation'] = Blender.Draw.Create(motionblur_deformation)
					self.id_geo_mb_deformation = self.draw_toggle('Motion blur deformation', 160, '_geo_mb_deformation',
						help = 'Enable motion blur deformation')

				self.line_feed()

				persistents['_geo_enable_proxy'] = Blender.Draw.Create(enable_proxy)
				self.id_geo_enable_proxy = self.draw_toggle('Enable proxy', 130, '_geo_enable_proxy',
					help = 'Enable proxy file')

				if (enable_proxy):

					proxy_file = property_string_get(self.active_obj, 'proxy_file')

					persistents['_geo_proxy_file'] = Blender.Draw.Create(proxy_file)

					self.draw_button('Proxy file:', 100, self.cb_proxy_filename,
						'Select proxy file', 0)

					self.id_geo_proxy_file = self.draw_string('', 410, 200, '_geo_proxy_file',
						help = 'Proxy file')

	def panel_textures(self):
		global persistents

		if (persistents['enable_textures'].val):
			self.draw_text(self.color_text, 'UV Col -> pretexture', 130, 2, 6)
			self.line_feed()

		self.draw_toggle('Enable', 100, 'enable_textures',
			help = 'Enable all textures')

		self.draw_toggle('Auto mipmap', 100, 'enable_automipmap',
			help = 'Automatically generate mipmap')

		self.draw_toggle('Texture TX', 100, 'enable_textures_tx',
			help = 'Change the textures extension to .tx')

		self.draw_toggle('Auto unpack', 100, 'enable_autounpack',
			help = 'Unpack and write temporary image texture')

		self.line_feed()

		self.draw_toggle('Enable UV map', 100, 'enable_uv',
			help = 'Enable UV mapping')

		if (persistents['enable_uv'].val):

			self.draw_toggle('UV flip U', 100, 'flip_u',
				help = 'Enable UV flip U')

			self.draw_toggle('UV flip V', 100, 'flip_v',
				help = 'Enable UV flip V')

			self.draw_toggle('UV layers', 100, 'enable_uvlayes',
				help = 'Enable export UV layers')

		self.line_feed()

		self.draw_string('Texture memory: ', 210, 30, 'limits_texturememory',
			help = 'Maximum texture cache size in kB')

		self.line_feed()

		self.draw_string('Texture files: ', 210, 30, 'limits_texturefiles',
			help = 'Maximum number of open texture file')

	def panel_shadows(self):
		global persistents

		self.id_shadow_maps = self.draw_toggle('Maps', 105, 'shadow_maps',
			self.cb_shadows, 'Enable shadow maps', sep = 0)

		self.id_shadow_woo = self.draw_toggle('Woo', 105, 'shadow_woo',
			self.cb_shadows, 'Enable Woo (average) shadow')

		self.id_shadow_raytraced = self.draw_toggle('Ray traced', 100, 'shadow_ray_traced',
			self.cb_shadows, 'Enable ray traced shadows')

		if (persistents['shadow_maps'].val or persistents['shadow_woo'].val):
			self.line_feed(False)

			self.draw_toggle('Dynamics', 210, 'enable_dynamic',
				help = 'Enable dynamic shadow')

			if (not persistents['enable_dynamic'].val):
				self.line_feed()

				self.draw_menu(self.menu_compression_tiff, 100, 'compression_shadow',
					help = 'Shadow compression')

	def panel_lights(self):
		global persistents

		if (persistents['enable_lights'].val):
			self.draw_text(self.color_text, 'Amb -> ambientlight | Lamp -> pointlight | Spot -> spotlight | Sun -> distantlight', 130, 2, 6)
			self.line_feed()

		self.draw_toggle('Enable', 100, 'enable_lights',
			help = 'Enable all lights')

		self.draw_toggle('Key Fill Rim', 100, 'enable_key_fill_rim',
			help = 'Enable Key-Fill-Rim lights')

		if (persistents['enable_lights'].val):

			self.draw_slider('Lights factor: ', 320, 0.0, 1000.0, 'lights_factor',
				help = 'Lights factor')

			self.line_feed()

			self.draw_button('Refresh object', 100,
				self.cb_refresh_active_object, 'Refresh active object')

			obj_ok = (self.active_obj and (self.active_obj.type == 'Lamp'))

			if (not obj_ok):

				self.draw_text(self.color_text, 'No lamp selected', 50, 2, 6)
			else:

				excluded = property_boolean_get(self.active_obj, 'excluded')

				self.draw_text(self.color_text, 'Lamp: "%s"%s' %
					(self.active_obj.name, (' (excluded)' if excluded else '')), 50, 2, 6)

				if (not excluded):

					if (persistents['enable_caustics'].val):

						self.line_feed()

						photon_map = property_boolean_get(self.active_obj, 'photon_map')

						persistents['_lamp_photon_map'] = Blender.Draw.Create(photon_map)
						self.id_lamp_photon_map = self.draw_toggle('Photon map', 100, '_lamp_photon_map',
							help = 'Enable photon map property')

			if (self.menu_light):

				# get all lights

				lights = Blender.Lamp.Get()
				if (lights):
					self.line_feed()

					self.menu_lamp = self.bake_menu('Lamps',
						[[l.name, l.name] for l in sorted(lights)])

					self.draw_menu(self.menu_lamp, 100, '_select_lamp',
						help = 'Select lamp')

					lamp_name = self.menu_lamp.convert(persistents['_select_lamp'].val)
					if (lights_assign[1].has_key(lamp_name)):

						l = lights_assign[1][lamp_name]

						self.draw_button('Remove', 100,
							self.cb_remove_light, 'Remove light')

						if (persistents['shadow_maps'].val or
							persistents['shadow_woo'].val or
							persistents['shadow_ray_traced'].val):

								self.line_feed()
								y = l.gui_shadow(self.x, self.y, self.h, self.s)

						self.line_feed()

						y = l.gui(self.x, self.y, self.h, self.s)

						self.blank(self.spd)

						self.draw_button('Default', 100,
							self.cb_light_default, 'Default values')

						self.y = y

					else:
						self.draw_button('Assign', 100,
							self.cb_assign_light, 'Assign light')

						self.draw_menu(self.menu_light, 100, '_select_light',
							self.cb_menu_light, 'Select shader')
	def panel_displacement(self):
		global persistents

		if (persistents['enable_displacements'].val):
			self.draw_text(self.color_text, 'UV Disp -> dispmap | Disp -> Km', 130, 2, 6)
			self.line_feed()


		self.draw_toggle('Enable', 100, 'enable_displacements', help = 'Enable displacements')

		if (persistents['enable_displacements'].val):
			self.draw_string('Max radius: ', 140, 20, 'maxradius',
				help = 'Maximum radial displacement')

			self.draw_string('Max space: ', 140, 20, 'maxspace',
				help = 'Coordinate system in which max radial displacement is measured')

	def panel_caustics(self):
		global persistents, materials_assign

		if (persistents['enable_caustics'].val):
			self.draw_text(self.color_text, 'IOR -> eta | specTransp -> Kt | rayMirr -> Kr | diffuseSize -> Kd | specSize -> Ks | roughness -> roughness', 130, 2, 6)
			self.line_feed(False)
			self.draw_text(self.color_text, 'spec color -> specularcolor | mir color -> transmitcolor', 130, 2, 6)
			self.line_feed()

		self.draw_toggle('Enable', 100, 'enable_caustics',
			help = 'Enable caustics')

		if (persistents['enable_caustics'].val):
			self.draw_number('Raytraced max depth: ', 170, 0, 16, 'caustics_max_depth',
				help = 'Ray traced max depth caustics')

			shader_shoot_photons = materials_assign[0]['shoot_photons']
			if (shader_shoot_photons is not None):
				self.line_feed()

				y = shader_shoot_photons.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100, self.cb_shoot_photons_default,
					'Shoot photons default values')

				self.y = y

			shader_caustic_light = lights_assign[0]['caustic_light']
			if (shader_caustic_light is not None):
				self.line_feed()

				y = shader_caustic_light.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100,
					self.cb_shader_caustic_light_default, 'Caustic light default values')

				self.y = y

	def panel_shaders(self):
		global persistents, materials_assign

		if (persistents['enable_shaders'].val):
			self.draw_text(self.color_text, 'Col -> C | A -> opacity', 130, 2, 6)
			self.line_feed()

		self.draw_toggle('Enable', 130, 'enable_shaders',
			help = 'Enable all shaders')

		if (persistents['enable_shaders'].val):

			mat_script = False

			self.draw_number('Shading quality: ', 160, 0.0, 16.0, 'shadingquality',
				help = 'Shading quality')

			self.draw_number('Limits gridsize: ', 150, 1, 1024, 'limits_gridsize',
				help = 'Maximum number of surface points at one time')

			self.line_feed()

			self.draw_toggle('Enable debug', 130, '_enable_debug_shaders',
				help = 'Enable debug shaders')

			if (persistents['_enable_debug_shaders'].val):

				if (self.menu_debug_shader):
					self.draw_menu(self.menu_debug_shader, 100, '_select_debug_shader',
						self.cb_debug_shader, help = 'Select debug shader')

					if (self.debug_shader is not None):
						self.line_feed()

						self.y = self.debug_shader.gui(self.x, self.y, self.h, self.s)
			else:
				if (self.menu_surface):

					# get all materials

					materials = Blender.Material.Get()

					if (not materials):

						self.active_mat = None

					else:

						self.menu_material = self.bake_menu('Materials',
							[[m.name, m.name] for m in sorted(materials)])

						material_name = self.menu_material.convert(persistents['_select_material'].val)

						self.active_mat = Blender.Material.Get(material_name)

						if (self.active_mat and persistents['enable_scripts'].val):

							l = 130

							texts = Blender.Text.Get()

							# postscript

							self.line_feed()

							enable_postscript = property_boolean_get(self.active_mat, 'enable_postscript')
							persistents['_mat_enable_postscript'] = Blender.Draw.Create(enable_postscript)
							self.id_mat_enable_postscript = self.draw_toggle('Shader post-script', 130, '_mat_enable_postscript',
								help = 'Enable shader post-script')

							if (enable_postscript):

								script = property_string_get(self.active_mat, 'postscript')

								if (script):
									self.draw_text(self.color_text, script, l, 2, 6)
								elif (texts):
									self.menu_postscript = self.bake_menu('Load post-script from text',
										[[t.name, t.name] for t in texts])

									self.draw_menu(self.menu_postscript, l, '_select_postscript',
										self.cb_menu_mat_postscript, 'Select shader post-script')

							# script

							self.line_feed()

							enable_script = property_boolean_get(self.active_mat, 'enable_script')
							persistents['_mat_enable_script'] = Blender.Draw.Create(enable_script)
							self.id_mat_enable_script = self.draw_toggle('Shader script', 130, '_mat_enable_script',
								help = 'Enable shader script')

							if (enable_script):

								script = property_string_get(self.active_mat, 'script')

								if (script):
									mat_script = True
									self.draw_text(self.color_text, script, l, 2, 6)
								elif (texts):
									self.menu_script = self.bake_menu('Load script from text',
										[[t.name, t.name] for t in texts])

									self.draw_menu(self.menu_script, l, '_select_script',
										self.cb_menu_mat_script, 'Select shader script')

							# prescript

							self.line_feed()

							enable_prescript = property_boolean_get(self.active_mat, 'enable_prescript')
							persistents['_mat_enable_prescript'] = Blender.Draw.Create(enable_prescript)
							self.id_mat_enable_prescript = self.draw_toggle('Shader pre-script', 130, '_mat_enable_prescript',
								help = 'Enable shader post-script')

							if (enable_prescript):

								script = property_string_get(self.active_mat, 'prescript')

								if (script):
									self.draw_text(self.color_text, script, l, 2, 6)
								elif (texts):
									self.menu_prescript = self.bake_menu('Load pre-script from text',
										[[t.name, t.name] for t in texts])

									self.draw_menu(self.menu_prescript, l, '_select_prescript',
										self.cb_menu_mat_prescript, 'Select shader pre-script')


						self.line_feed()

						self.draw_menu(self.menu_material, 130, '_select_material',
							help = 'Select material')

						if (not mat_script):

							if (materials_assign[1].has_key(material_name)):

								m = materials_assign[1][material_name]

								self.draw_button('Remove', 130,
									self.cb_remove_material, 'Remove assign')

								if (persistents['enable_bake_diffuse'].val):

									self.line_feed()
									y = m.gui_sss(self.x, self.y, self.h, self.s)

								self.line_feed()

								y = m.gui(self.x, self.y, self.h, self.s)

								self.blank(self.spd)

								self.draw_button('Default', 130,
									self.cb_material_default, 'Default values')

								self.y = y
							else:
								self.draw_button('Assign', 130,
									self.cb_assign_material, 'Assign material')

								self.draw_menu(self.menu_surface, 130, '_select_surface',
									self.cb_menu_surface, 'Select shader')

	def panel_dof(self):
		global persistents

		self.draw_toggle('Enable', 100, 'enable_dof', help = 'Enable Depth Of Field')

		if (persistents['enable_dof'].val):
			self.draw_string('F/Stop: ', 100, 20, 'fstop',
				help = 'F/Stop for depth of field')

			self.draw_string('Focal length: ', 160, 20, 'focallength',
				help = 'Lens focal length')

			self.draw_number('Quality: ', 100, 1, 256, 'dofquality',
				help = 'Number of lens values for DoF')

	def panel_environment(self):
		global persistents

		self.draw_toggle('Sky', 60, 'enable_sky',
			help = 'Enable background color')

		self.draw_text(self.color_text, 'Units:', 30, 2, 6)

		self.draw_menu(self.menu_units, 100, 'units_length',
			help = 'Physical length units of "common" space')

		if (persistents['units_length'].val):
			self.draw_string('Length scale: ', 140, 20, 'units_lengthscale',
				help = 'Length unit scale of "common" space units')

		if (persistents['enable_scripts'].val):

			l = 130

			texts = Blender.Text.Get()

			self.line_feed()

			self.id_enable_world_postscript = self.draw_toggle('World post-script', 130, 'enable_world_postscript',
				help = 'Enable world post-script')

			if (persistents['enable_world_postscript'].val):

				script = persistents['world_postscript'].val

				if (script):

					self.draw_text(self.color_text, script, l, 2, 6)

				elif (texts):
					self.menu_postscript = self.bake_menu('Load post-script from text',
						[[t.name, t.name] for t in texts])

					self.draw_menu(self.menu_postscript, l, '_select_postscript',
						self.cb_menu_world_postscript, 'Select post-script')

			self.line_feed()

			self.id_enable_header_prescript = self.draw_toggle('World pre-script', 130, 'enable_world_prescript',
				help = 'Enable world pre-script')

			if (persistents['enable_world_prescript'].val):

				script = persistents['world_prescript'].val

				if (script):

					self.draw_text(self.color_text, script, l, 2, 6)

				elif (texts):
					self.menu_prescript = self.bake_menu('Load pre-script from text',
						[[t.name, t.name] for t in texts])

					self.draw_menu(self.menu_prescript, l, '_select_prescript',
						self.cb_menu_world_prescript, 'Select pre-script')


	def panel_ambient_occlusion(self):
		global persistents, materials_assign

		self.draw_toggle('Enable', 100, 'enable_ambient_occlusion',
			help = 'Enable ambient occlusion')

		if (persistents['enable_ambient_occlusion'].val):

			shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
			if (shader_ambient_occlusion):
				self.line_feed()

				y = shader_ambient_occlusion.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100, self.cb_ambient_occlusion_default,
					'Ambient occlusion default values')

				self.y = y

			shader_environment_light = lights_assign[0]['environment_light']
			if (shader_environment_light):
				self.line_feed()

				y = shader_environment_light.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100,
					self.cb_shader_envlight_default, 'Environment light default values')

				self.y = y

	def panel_indirect_light(self):
		global persistents, lights_assign

		self.draw_toggle('Enable', 100, 'enable_indirect_light',
			help = 'Enable indirect light')

		if (persistents['enable_indirect_light'].val):
			shader_indirect_light = lights_assign[0]['indirect_light']
			if (shader_indirect_light is not None):

				self.draw_number('Min samples: ', 140, 0, 16, 'indirect_minsamples',
					help = 'The minimum number of nearby samples')

				self.line_feed()

				y = shader_indirect_light.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100,
					self.cb_shader_indirect_light_default, 'Indirect light default values')

				self.y = y

	def panel_ray_traced(self):
		global persistents

		self.draw_toggle('Enable', 100, 'enable_ray_traced',
			help = 'Enable ray traced reflections and refractions')

		if (persistents['enable_ray_traced'].val):
			if (persistents['shadow_ray_traced'].val):
				self.draw_number('Shadow bias: ', 140, 0, 16, 'ray_traced_shadow_bias',
					help = 'Ray traced shadow bias')

			self.draw_number('Raytraced max depth: ', 170, 0, 32, 'ray_traced_max_depth',
				help = 'Ray traced max depth')

			self.line_feed()

			self.draw_toggle('Opaque shadows', 100, 'ray_traced_opaque_shadows',
				help = 'Enable objects opaque regardless of their shaders')

			self.draw_toggle('Ray displace', 100, 'ray_displace',
				help = 'Enable displace objects when ray tracing')

			self.draw_toggle('Ray motion', 100, 'ray_motion',
				help = 'Do rays consider motion-blur of objects')

	def panel_sss(self):
		global persistents

		self.draw_toggle('Enable', 100, 'enable_bake_diffuse',
			help = 'Enable bake diffuse')

		if (persistents['enable_bake_diffuse'].val):
			shader_bake_diffuse = materials_assign[0]['bake_diffuse']
			if (shader_bake_diffuse is not None):
				self.line_feed()

				y = shader_bake_diffuse.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100, self.cb_shader_bake_diffuse_default,
					'Bake diffuse default values')

				self.y = y

	def panel_scripts(self):
		global persistents

		self.draw_toggle('Enable', 130, 'enable_scripts',
			help = 'Enable scripts')

		if (persistents['enable_scripts'].val):

			l = 130

			texts = Blender.Text.Get()

			self.line_feed()

			self.id_enable_header_postscript = self.draw_toggle('Header post-script', 130, 'enable_header_postscript',
				help = 'Enable header post-script')

			if (persistents['enable_header_postscript'].val):

				script = persistents['header_postscript'].val

				if (script):

					self.draw_text(self.color_text, script, l, 2, 6)

				elif (texts):
					self.menu_postscript = self.bake_menu('Load post-script from text',
						[[t.name, t.name] for t in texts])

					self.draw_menu(self.menu_postscript, l, '_select_postscript',
						self.cb_menu_header_postscript, 'Select post-script')

			self.line_feed()

			self.id_enable_header_prescript = self.draw_toggle('Header pre-script', 130, 'enable_header_prescript',
				help = 'Enable header pre-script')

			if (persistents['enable_header_prescript'].val):

				script = persistents['header_prescript'].val

				if (script):

					self.draw_text(self.color_text, script, l, 2, 6)

				elif (texts):
					self.menu_prescript = self.bake_menu('Load pre-script from text',
						[[t.name, t.name] for t in texts])

					self.draw_menu(self.menu_prescript, l, '_select_prescript',
						self.cb_menu_header_prescript, 'Select pre-script')

	def panel_stereo(self):
		global persistents

		self.draw_toggle('Enable', 100, 'enable_stereo',
			help = 'Enable stereo rendering')

		if (persistents['enable_stereo'].val):
			self.draw_menu(self.menu_stereo_projection, 100, 'stereo_projection',
				help = 'Projection for stereo cameras')

			self.draw_menu(self.menu_stereo_shade, 100, 'stereo_shade',
				help = 'Which view to shade for stereo cameras')

			self.draw_string('Separation: ', 155, 20, 'stereo_separation',
				help = 'Camera separation for stereo cameras')

			self.draw_string('Convergence: ', 155, 20, 'stereo_convergence',
				help = 'Convergence distance for stereo cameras')

	def panel_motion_blur(self):
		global persistents

		self.draw_toggle('Enable', 100, 'enable_motion_blur',
			help = 'Enable motion blur')

		if (persistents['enable_motion_blur'].val):
			self.draw_string('Shutter open: ', 180, 20, 'shutter_open',
				help = 'Shutter open time for motion blur')

			self.draw_string('Shutter close: ', 180, 20, 'shutter_close',
				help = 'Shutter close time for motion blur')

			self.line_feed()

			self.draw_number('Quality: ', 100, 1, 256, 'temporal_quality',
				help = 'Number of time values for motion blur')

			self.draw_number('Frames transformation: ', 180, 2, 9999, 'frames_transformation',
				help = 'Number of frames moion blur transformation')

			self.draw_number('Frames deformation: ', 180, 2, 9999, 'frames_deformation',
				help = 'Number of frames moion blur deformation')

			self.line_feed()

			self.draw_number('Motion factor: ', 140, 0.0, 1000.0, 'dice_motionfactor',
				help = 'Scaling for decreased tessellation and shading for moving objects')

# property

def property_set(obj, name, value):

	def __property_set__(obj, name, value):
		try:
			if (obj.properties.has_key('gelato')):
				obj.properties['gelato'][name] = value
			else:
				obj.properties['gelato'] = {name: value}
		except:
			sys.excepthook(*sys.exc_info())


	if (type(obj) is list):
		for x in obj:
			__property_set__(x, name, value)
	else:
		__property_set__(obj, name, value)


def property_get(obj, name):
	return obj.properties['gelato'][name]

def property_boolean_get(obj, name, default = False):
	try:
		return property_get(obj, name) != 0
	except:
		return default

def property_string_get(obj, name, default = ''):
	try:
		return property_get(obj, name)
	except:
		return default

def selected_object(types = []):
	selected = Blender.Object.GetSelected()
	if (selected):
		obj = selected[0]
		if (not types):
			return obj
		if (obj.type in types):
			return obj
	return None

# XML data

def default_values():
	global WINDOWS, FILENAME_PYG, persistents

	path_shader    = ':'.join(['.', os.path.join('$GELATOHOME', 'shaders'),  '&'])
	path_texture   = ':'.join(['.', os.path.join('$GELATOHOME', 'textures'), '&'])
	path_inputs    = ':'.join(['.', os.path.join('$GELATOHOME', 'inputs'),   '&'])
	path_imageio   = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])
	path_generator = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])

	texturefiles = ('100' if (WINDOWS) else '1000')

	persistents = {
		'filename':			Blender.Draw.Create(FILENAME_PYG),

		'files_extensions':		Blender.Draw.Create(0),		# file.NNN.ext

		'enable_binary':		Blender.Draw.Create(0),
		'enable_split':			Blender.Draw.Create(0),
		'enable_anim':			Blender.Draw.Create(0),
		'enable_relative_paths':	Blender.Draw.Create(1),

		'enable_auto_threads':		Blender.Draw.Create(1),
		'limits_threads':		Blender.Draw.Create(1),

		'enable_scripts':		Blender.Draw.Create(1),
		'enable_header_postscript':	Blender.Draw.Create(0),
		'header_postscript':		Blender.Draw.Create(''),
		'enable_header_prescript':	Blender.Draw.Create(0),
		'header_prescript':		Blender.Draw.Create(''),
		'_select_script':		Blender.Draw.Create(0),
		'_select_postscript':		Blender.Draw.Create(0),
		'_select_prescript':		Blender.Draw.Create(0),

		'bucketorder':			Blender.Draw.Create(2),		# Spiral
		'bucketsize_x':			Blender.Draw.Create(32),
		'bucketsize_y':			Blender.Draw.Create(32),

		'enable_error':			Blender.Draw.Create(0),
		'error_filename':		Blender.Draw.Create('>>gelato_log.txt'),

		'enable_preview':		Blender.Draw.Create(0),
		'preview_quality':		Blender.Draw.Create(0.1),

		'enable_viewer':		Blender.Draw.Create(1),
		'format':			Blender.Draw.Create(0),		# Null
		'data':				Blender.Draw.Create(0),		# RGB

		'compression':			Blender.Draw.Create(1),		# ZIP
		'compression_shadow':		Blender.Draw.Create(1),		# ZIP

		'shadow_maps':			Blender.Draw.Create(0),
		'shadow_woo':			Blender.Draw.Create(0),
		'shadow_ray_traced':		Blender.Draw.Create(0),
		'enable_dynamic':		Blender.Draw.Create(0),

		'antialiasing_x':		Blender.Draw.Create(4),
		'antialiasing_y':		Blender.Draw.Create(4),

		'filter':			Blender.Draw.Create(0),		# Gaussian
		'filterwidth_x':		Blender.Draw.Create(2.0),
		'filterwidth_y':		Blender.Draw.Create(2.0),

		'gamma':			Blender.Draw.Create(1.0),
		'gain':				Blender.Draw.Create(1.0),

		'dither':			Blender.Draw.Create(0.5),

		'quantize_zero':		Blender.Draw.Create('0'),
		'quantize_one':			Blender.Draw.Create('255'),
		'quantize_min':			Blender.Draw.Create('0'),
		'quantize_max':			Blender.Draw.Create('255'),

		'all_double_sided':		Blender.Draw.Create(0),
		'enable_dupli_verts':		Blender.Draw.Create(1),
		'enable_vextex_color':		Blender.Draw.Create(1),
		'enable_halos':			Blender.Draw.Create(1),

		'enable_ray_traced':		Blender.Draw.Create(0),
		'ray_traced_max_depth':		Blender.Draw.Create(1),
		'ray_traced_shadow_bias':	Blender.Draw.Create(0.01),
		'ray_traced_opaque_shadows':	Blender.Draw.Create(1),
		'ray_motion':			Blender.Draw.Create(0),
		'ray_displace':			Blender.Draw.Create(1),

		'lights_factor':		Blender.Draw.Create(50.0),
		'enable_key_fill_rim':		Blender.Draw.Create(0),
		'enable_lights':		Blender.Draw.Create(1),
		'enable_caustics':		Blender.Draw.Create(0),
		'caustics_max_depth':		Blender.Draw.Create(4),
		'_select_lamp':			Blender.Draw.Create(0),
		'_select_light':		Blender.Draw.Create(0),

		'enable_shaders':		Blender.Draw.Create(1),
		'shadingquality':		Blender.Draw.Create(1.0),
		'limits_gridsize':		Blender.Draw.Create(256),
		'_enable_debug_shaders':	Blender.Draw.Create(0),
		'_select_debug_shader':		Blender.Draw.Create(0),
		'_select_material':		Blender.Draw.Create(0),
		'_select_surface':		Blender.Draw.Create(0),

		'enable_displacements':		Blender.Draw.Create(0),
		'maxradius':			Blender.Draw.Create('0.0'),
		'maxspace':			Blender.Draw.Create('common'),

		'enable_ambient_occlusion':	Blender.Draw.Create(0),

		'enable_bake_diffuse':		Blender.Draw.Create(0),

		'enable_indirect_light':	Blender.Draw.Create(0),
		'indirect_minsamples':		Blender.Draw.Create(3),

		'enable_textures':		Blender.Draw.Create(1),
		'enable_automipmap':		Blender.Draw.Create(1),
		'enable_autounpack':		Blender.Draw.Create(0),
		'enable_textures_tx':		Blender.Draw.Create(0),
		'enable_uvlayes':		Blender.Draw.Create(0),
		'enable_uv':			Blender.Draw.Create(1),
		'flip_u':			Blender.Draw.Create(0),
		'flip_v':			Blender.Draw.Create(1),

		'enable_dof':			Blender.Draw.Create(0),
		'fstop':			Blender.Draw.Create('4.0'),
		'focallength':			Blender.Draw.Create('0.032'),
		'dofquality':			Blender.Draw.Create(16),

		'enable_sky':			Blender.Draw.Create(1),
		'units_length':			Blender.Draw.Create(0),		# none
		'units_lengthscale':		Blender.Draw.Create('1.0'),
		'enable_world_postscript':	Blender.Draw.Create(0),
		'world_postscript':		Blender.Draw.Create(''),
		'enable_world_prescript':	Blender.Draw.Create(0),
		'world_prescript':		Blender.Draw.Create(''),

		'limits_texturememory':		Blender.Draw.Create('20480'),
		'limits_texturefiles':		Blender.Draw.Create(texturefiles),

		'path_shader':			Blender.Draw.Create(path_shader),
		'path_texture':			Blender.Draw.Create(path_texture),
		'path_inputs':			Blender.Draw.Create(path_inputs),
		'path_imageio':			Blender.Draw.Create(path_imageio),
		'path_generator':		Blender.Draw.Create(path_generator),

		'pass_beauty':			Blender.Draw.Create(1),
		'pass_shadows':			Blender.Draw.Create(0),
		'pass_ambient_occlusion':	Blender.Draw.Create(0),
		'pass_photon_maps':		Blender.Draw.Create(0),
		'pass_bake_diffuse':		Blender.Draw.Create(0),

		'enable_stereo':		Blender.Draw.Create(0),
		'stereo_separation':		Blender.Draw.Create('0'),
		'stereo_convergence':		Blender.Draw.Create('0'),
		'stereo_projection':		Blender.Draw.Create(0),		# off-axis
		'stereo_shade':			Blender.Draw.Create(1),		# center

		'enable_motion_blur':		Blender.Draw.Create(0),
		'shutter_open':			Blender.Draw.Create('0.0'),
		'shutter_close':		Blender.Draw.Create('0.5'),
		'temporal_quality':		Blender.Draw.Create(16),
		'frames_transformation':	Blender.Draw.Create(2),
		'frames_deformation':		Blender.Draw.Create(2),
		'dice_motionfactor':		Blender.Draw.Create(1.0),

		'enable_rerender':		Blender.Draw.Create(0),
		'rerender_memory':		Blender.Draw.Create(''),

		'_obj_excluded':		Blender.Draw.Create(0),
		'_obj_enable_postscript':	Blender.Draw.Create(0),
		'_obj_enable_prescript':	Blender.Draw.Create(0),

		'_geo_catmull_clark':		Blender.Draw.Create(0),
		'_geo_raster_width':		Blender.Draw.Create(0),
		'_geo_bake_diffuse':		Blender.Draw.Create(0),
		'_geo_indirect_light':		Blender.Draw.Create(0),
		'_geo_mb_transformation':	Blender.Draw.Create(0),
		'_geo_mb_deformation':		Blender.Draw.Create(0),
		'_geo_enable_proxy':		Blender.Draw.Create(0),
		'_geo_proxy_file':		Blender.Draw.Create(''),

		'_lamp_photon_map':		Blender.Draw.Create(0),

		'_mat_enable_script':		Blender.Draw.Create(0),
		'_mat_enable_postscript':	Blender.Draw.Create(0),
		'_mat_enable_prescript':	Blender.Draw.Create(0),

		'_panel_output':		Blender.Draw.Create(1),
		'_panel_images':		Blender.Draw.Create(0),
		'_panel_pass':			Blender.Draw.Create(0),
		'_panel_ambient_occlusion':	Blender.Draw.Create(0),
		'_panel_objects':		Blender.Draw.Create(0),
		'_panel_geometries':		Blender.Draw.Create(0),
		'_panel_lights':		Blender.Draw.Create(0),
		'_panel_shadows':		Blender.Draw.Create(0),
		'_panel_textures':		Blender.Draw.Create(0),
		'_panel_shaders':		Blender.Draw.Create(0),
		'_panel_displacement':		Blender.Draw.Create(0),
		'_panel_dof':			Blender.Draw.Create(0),
		'_panel_environment':		Blender.Draw.Create(0),
		'_panel_indirectlight':		Blender.Draw.Create(0),
		'_panel_ray_traced':		Blender.Draw.Create(0),
		'_panel_sss':			Blender.Draw.Create(0),
		'_panel_caustics':		Blender.Draw.Create(0),
		'_panel_scripts':		Blender.Draw.Create(0),
		'_panel_stereo':		Blender.Draw.Create(0),
		'_panel_motion_blur':		Blender.Draw.Create(0),
		'_panel_rerender':		Blender.Draw.Create(0),

		'$pack_config':			Blender.Draw.Create(0),
	}

	for mat in materials_assign[1:]:
		for sd in mat.itervalues():
			if (sd is not None):
				sd.default()

	for lig in lights_assign[1:]:
		for sd in lig.itervalues():
			if (sd is not None):
				sd.default()

def output_filename_xml():
	global persistents

	base = ''

	try:
		(directory, filename) = os.path.split(persistents['filename'].val)
		(base, ext) = os.path.splitext(filename)
	except:
		pass

	if (not base):
		base = 'gelato'

	return	fix_file_name(base + '.xml')

def config_save():
	global ROOT_ELEMENT, USE_XML_DOM_EXT
	global materials_assign, lights_assign
	global persistents

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

	sc = Blender.Scene.GetCurrent()

	for name in sorted(persistents.iterkeys()):
		c = name[0]
		# skip internal's names
		if (c == '_'):
			continue
		# save and skip property
		elif (c == '$'):
			property_set(sc, name[1:], persistents[name].val)
			continue

		elem = doc.createElement(name)
		head.appendChild(elem)
		elem.appendChild(doc.createTextNode(str(persistents[name].val).strip()))

	# materials

	blender_materials = [m.name for m in Blender.Material.Get()]

	for idx, ml in enumerate(materials_assign):
		materials = doc.createElement('materials')
		root.appendChild(materials)
		materials.setAttribute('index', str(idx))

		for mat in sorted(ml.iterkeys()):

			if ((idx > 0) and (mat not in blender_materials)):
				continue

			sd = ml[mat]
			if (sd is None):
				continue

			material = doc.createElement('material')
			materials.appendChild(material)
			material.setAttribute('name', mat)

			if ((idx > 0) and (sd.widget_enable_sss.val)):
				material.setAttribute('enable_sss', str(sd.widget_enable_sss.val))
				material.setAttribute('sss_parameter', sd.widget_sss.val)

			sd.toxml(doc, material)

	# lights

	for idx, lg in enumerate(lights_assign):
		lights = doc.createElement('lights')
		root.appendChild(lights)
		lights.setAttribute('index', str(idx))

		for lig in sorted(lg.iterkeys()):

			sd = lg[lig]
			if (sd is None):
				continue

			light = doc.createElement('light')
			lights.appendChild(light)
			light.setAttribute('name', lig)

			if ((idx > 0) and (sd.widget_enable_shadow.val)):
				light.setAttribute('enable_shadow', str(sd.widget_enable_shadow.val))
				light.setAttribute('shadow_parameter', sd.widget_shadow.val)

			sd.toxml(doc, light)

	# write XML file

	if (persistents['$pack_config'].val):

		name_xml = output_filename_xml()

		# delete text file

		try:
			Blender.Text.unlink(Blender.Text.Get(name_xml))
		except:
			pass

		# add text file

		try:
			text = Blender.Text.New(name_xml)

			if (USE_XML_DOM_EXT):
				xml.dom.ext.PrettyPrint(doc, text)
			else:
				text.write( doc.toprettyxml(indent = '  ', newl = '\n') )
		except:
			sys.excepthook(*sys.exc_info())

	else:
		filename_xml = output_filename_xml()

		try:
			fxml = open_temp_rename(filename_xml, 'w')

		except IOError:

			print 'Error: Cannot write file "%s"' % filename_xml
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

def config_load():
	global ROOT_ELEMENT
	global materials_assign, lights_assign
	global persistents

	sc = Blender.Scene.GetCurrent()

	for name in persistents.iterkeys():

		# load property
		if (name[0] == '$'):
			try:
				val = property_get(sc, name[1:])

				ty = type(persistents[name].val)
				if (ty is int):
					persistents[name] = Blender.Draw.Create(int(val))
				elif (ty is float):
					persistents[name] = Blender.Draw.Create(float(val))
				elif (ty is str):
					persistents[name] = Blender.Draw.Create(val.strip())
				else:
					print 'Error: element "%s" type "%s" unknow' % (name, ty)

			except:
				pass

	if (persistents['$pack_config'].val):

		# read pack xml file

		name_xml = output_filename_xml()

		try:
			text = Blender.Text.Get(name_xml)

			doc = xml.dom.minidom.parseString(''.join(text.asLines()))

		except:
			print 'Info: XML config "%s" not found, will use default settings' % name_xml
			return
	else:
		# read xml file

		filename_xml = output_filename_xml()

		try:
			doc = xml.dom.minidom.parse(filename_xml)
		except:
			print 'Info: XML config file "%s" not found, will use default settings' % filename_xml
			return

	if (doc.documentElement.tagName != ROOT_ELEMENT):
		print 'Error: file "%s", invalid root element "%s"' % (filename_xml, doc.documentElement.tagName)
		return

	head = doc.getElementsByTagName('config')
	if (len(head) == 0):
		print 'Error: file "%s", not element "config"' % filename_xml
	else:
		for name in persistents.iterkeys():

			# skip internal's names
			if (name[0] in ['_', '$']):
				continue

			el = head[0].getElementsByTagName(name)
			if (len(el) == 0):
				continue

			el[0].normalize()
			nd = el[0].firstChild
			if (nd.nodeType != xml.dom.Node.TEXT_NODE):
				continue

			try:
				ty = type(persistents[name].val)
				if (ty is int):
					persistents[name] = Blender.Draw.Create(int(nd.data))
				elif (ty is float):
					persistents[name] = Blender.Draw.Create(float(nd.data))
				elif (ty is str):
					persistents[name] = Blender.Draw.Create(nd.data.strip())
				else:
					print 'Error: file "%s", element "%s" type "%s" unknow' % (filename_xml, name, ty)
			except:
				sys.excepthook(*sys.exc_info())

	# materials

	blender_materials = [m.name for m in Blender.Material.Get()]

	for material in doc.getElementsByTagName('materials'):
		index = material.getAttribute('index')
		if (index is None):
			print 'Error: file "%s", not attribute "index" element "materials"' % filename_xml
			continue

		idx = int(index)

		for mat in material.getElementsByTagName('material'):

			name = mat.getAttribute('name')
			if (name is None):
				continue

			if ((idx > 0) and (name not in blender_materials)):
				continue

			sd = shader()

			if (not sd.fromxml(mat)):
				continue

			try:
				enable_sss = mat.getAttribute('enable_sss')
				if (enable_sss):
					sd.widget_enable_sss = Blender.Draw.Create(int(enable_sss))
			except:
				sys.excepthook(*sys.exc_info())

			try:
				sss_parameter = mat.getAttribute('sss_parameter')
				if (sss_parameter):
					sd.widget_sss = Blender.Draw.Create(sss_parameter.strip())
			except:
				sys.excepthook(*sys.exc_info())

			materials_assign[idx][name] = sd

	# lights

	for light in doc.getElementsByTagName('lights'):
		index = light.getAttribute('index')
		if (index is None):
			print 'Error: file "%s", not attribute "index" element "lights"' % filename_xml
			continue

		idx = int(index)

		for lig in light.getElementsByTagName('light'):

			name = lig.getAttribute('name')
			if (name is None):
				continue

			sd = shader()

			if (not sd.fromxml(lig)):
				continue

			try:
				enable_shadow = lig.getAttribute('enable_shadow')
				if (enable_shadow):
					sd.widget_enable_shadow = Blender.Draw.Create(int(enable_shadow))
			except:
				sys.excepthook(*sys.exc_info())

			try:
				shadow_parameter = lig.getAttribute('shadow_parameter')
				if (shadow_parameter):
					sd.widget_shadow = Blender.Draw.Create(shadow_parameter.strip())
			except:
				sys.excepthook(*sys.exc_info())

			lights_assign[idx][name] = sd

# utility

_uniq_gui_id = 0
_gui_id_memo = {}
def get_gui_id(global_id):
	global _uniq_gui_id, _gui_id_memo
	if (_gui_id_memo.has_key(global_id)):
		return _gui_id_memo[global_id]
	_uniq_gui_id += 1
	if (_uniq_gui_id > 16381):
		_uniq_gui_id = 1
	_gui_id_memo[global_id] = _uniq_gui_id
	return _uniq_gui_id

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
	global WINDOWS

	if (WINDOWS):
		# replace $var to %var%
		return re.sub('\$(\w+)', '%\\1%', name)
	return name

def search_file(name, paths):
	for p in paths.split(':'):
		try:
			path = os.path.expandvars(p)
			file = os.path.join(path, name)
			if (os.path.exists(file)):
				return file
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
	global ROOT_ELEMENT, FILENAME_PYG, INTERACTIVE
	global GELATO, GSOINFO, MAKETX, WINDOWS
	global materials_assign, lights_assign
	global persistents, gelato_gui, pyg

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 5

	if (sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR)):
		raise ('Error: Python version %d.%d or greater is required\nPython version is %s' % (PYTHON_MAJOR, PYTHON_MINOR, sys.version))

	ROOT_ELEMENT = 'BlenderGelato'

	# blender's mode

	INTERACTIVE = Blender.mode == 'interactive'

	# programs

	GELATO	= 'gelato'
	GSLC    = 'gslc'
	GSOINFO = 'gsoinfo'
	MAKETX	= 'maketx'

	if (sys.platform[:3] == 'win'):
		WINDOWS = True

		exe = '.exe'
		GELATO	+= exe
		GSLC    += exe
		GSOINFO += exe
		MAKETX	+= exe
	else:
		WINDOWS = False

	gelatohome = os.getenv('GELATOHOME')
	if (gelatohome):
		print 'Info: GELATOHOME = "%s".' % gelatohome

		bin = os.path.join(gelatohome, 'bin')

		GELATO	= fix_file_name(os.path.join(bin, GELATO))
		GSLC	= fix_file_name(os.path.join(bin, GSLC))
		GSOINFO = fix_file_name(os.path.join(bin, GSOINFO))
		MAKETX	= fix_file_name(os.path.join(bin, MAKETX))
	else:
		print 'Info: GELATOHOME environment variable not set.'

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

	FILENAME_PYG = base + '.pyg'

	# materials

	materials_assign = [{}, {}]

	# displacements TODO

	displacements_assign = [{}, {}]

	# lights

	lights_assign = [{}, {}]

	# default values

	default_values()

	# gelato convert

	pyg = gelato_pyg()

	# GUI

	gelato_gui = cfggui()

	# rename old config file
			
	filename = output_filename_xml()
	filename_old = filename + '.old'
			
	try:
		shutil.copyfile(filename, filename_old)
	except:
		sys.excepthook(*sys.exc_info())

	# load and save config file

	config_load()
	config_save()

	# start

	if (INTERACTIVE):
		# display GUI
		Blender.Draw.Register(gelato_gui.draw, gelato_gui.handle_event, gelato_gui.handle_button_event)
	else:
		# export scene
		gelato_gui.cb_save(0)

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

#	pycallgraph.make_dot_graph('/tmp/gelato.png')
#	pycallgraph.make_dot_graph('/tmp/gelato.pdf', format='pdf')

