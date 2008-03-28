#!BPY

"""
Name: 'Blender Gelato'
Blender: 245
Group: 'Render'
Tooltip: 'Render with NVIDIA Gelato(TM)'
"""

__author__ = 'Mario Ambrogetti'
__version__ = '0.16'
__url__ = ['http://wiki.blender.org/index.php/Scripts/Catalog/Render#blendergelato']
__bpydoc__ = """\
Blender to NVIDIA Gelato(TM)
"""

# NVIDIA Gelato(TM) Exporter
#
# Original By: Mario Ambrogetti
# Date:        Thu, 24 May 2007 13:25:46 +0200
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
import sys, os, math, tempfile, struct
import re, datetime, fnmatch, copy
import xml.dom.minidom

try:
	import xml.dom.ext
	USE_XML_DOM_EXT = True
except:
	USE_XML_DOM_EXT = False

try:
	import getpass
	USE_GETPASS = True
except:
	USE_GETPASS = False

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
		else:
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
		global WIN

		try:
			self.fd.close()
		except:
			sys.excepthook(*sys.exc_info())

		if (WIN and os.path.exists(self.filename)):
			try:
				os.unlink(self.filename)
			except:
				pass
		try:
			os.rename(self.tmpname, self.filename)
		except:
			sys.excepthook(*sys.exc_info())

class shader(object):
	class parameter(object):
		__slots__ = ['type', 'help', 'default', 'change', 'widget_gui', 'id_gui']

		def __init__(self, type, value, help):
			self.type    = type
			self.help    = help
			self.default = value
			self.change  = False

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

	__slots__ = ['literals', 'types', 'file', 'nameid', 'verbose', 'size', \
		'parameters', 'type', 'name', 'cmd_mask', \
		'widget_enable_sss',  'id_enable_sss', \
		'widget_sss', 'id_sss', \
		'widget_enable_shadow', 'id_enable_shadow',
		'widget_shadow', 'id_shadow']

	def __init__(self, file = None, nameid = '', verbose = 1):
		global WIN

		self.literals = enum_type('float', 'string', 'color', 'point', 'vector', 'normal', 'matrix')
		self.types    = enum_type('surface', 'displacement', 'volume', 'light', 'generic')

		self.file	= file
		self.nameid	= nameid
		self.verbose	= verbose
		self.size	= 210
		self.parameters = {}
		self.type	= None
		self.name	= None

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

		if (WIN) :
			self.cmd_mask = '""%s" "%s""'
		else:
			self.cmd_mask = '"%s" "%s"'

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
		return enumerate(self.parameters.keys())

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
			if (self.verbose > 1):
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
					if (self.verbose > 1):
						print 'Error: parameter not valid "%s"' % par.widget_gui.val
					continue

			# string

			elif (ty is self.literals.string):
				slist.append('Parameter ("string %s", "%s")\n' %
					(name, par.widget_gui.val.strip()))

			# color, point vector, normal

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
					if (self.verbose > 1):
						print 'Error: parameter not valid "%s"' % par.widget_gui.val
					continue

			# TODO matrix

			else:
				if (self.verbose > 1):
					print 'Error: unknow parameter "%s"' % name

		ty = self.type

		# Shader: surface, displacement, volume, generic

		if (ty in [self.types.surface, self.types.displacement, self.types.volume, self.types.generic]):
			slist.append('Shader ("%s", "%s")\n' % (self.types[ty], self.name))

		# Shader: light

		elif (ty is self.types.light):
			slist.append('Light ("%s", "%s")\n' % (self.nameid, self.name))

		else:
			if (self.verbose > 1):
				print 'Error: unknow type shader "%s"' % self.types[ty]
			return ''

		return ''.join(slist)

	def default(self):
		for val in self.parameters.itervalues():
			val.widget_gui = Blender.Draw.Create(val.default)
			val.change = False

	def update(self, id):
		for val in self.parameters.itervalues():
			if (val.id_gui == id):
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
				if (self.verbose > 1):
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
			fd = os.popen(cmd, 'r')
		except:
			if (self.verbose > 0):
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
			if (self.verbose > 1):
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
				if (self.verbose > 1):
					print 'Error: unknow parameter type "%s"' % elements
				continue

			par_name = None
			par      = None

			lit = self.literals[elements[0]]

			# float

			if ((lit is self.literals.float) and (l >= 3)):
				par_name = elements[1]
				par      = self.parameter(lit, elements[2], 'float %s' % par_name)

			# string

			elif ((lit is self.literals.string) and (l >= 3)):
				par_name = elements[1]
				par      = self.parameter(lit, elements[2][1:-1], 'string %s' % par_name)

			# color, point, vector, normal

			elif ((lit in [self.literals.color, self.literals.point, self.literals.vector, self.literals.normal]) and (l >= 3)):
				try:
					if ((l >= 7) and (elements[2] == '[' and elements[6] == ']')):
						val = '%s %s %s' % (elements[3], elements[4], elements[5])
					else:
						val = elements[2]
				except:
					val = elements[2]

				par_name = elements[1]
				par      = self.parameter(lit, val, '%s %s' % (self.literals[lit], par_name))

			# TODO matrix

			if ((par_name is None) or (par is None)):
				if (self.verbose > 1):
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
			fd = search_file(filename, permanents['path_shader'].val)
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
			self.__init__(shfile, nid)
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
			if (self.pyg.frame is None):
				return '%s%s%s' % (self.pyg.base, self.name, self.ext)
			else:
				if (self.suffix and self.pyg.files_extensions):
					# file.ext.NNN
					return '%s%s%s%s' % (self.pyg.base, self.name, self.ext, self.pyg.mask % self.pyg.frame)
				else:
					# file.NNN.ext
					return '%s%s%s%s' % (self.pyg.base, self.name, self.pyg.mask % self.pyg.frame, self.ext)

	class data_geometry(object):
		__slots__ = ['materials', 'nverts', 'verts']

		def __init__(self, material, nvert):
			self.materials = [material]
			self.nverts    = [nvert]
			self.verts     = []

		def append(self, material, nvert):
			self.materials.append(material)
			self.nverts.append(nvert)

		def append_vert(self, vert):
			self.verts.append(vert)

	class data_texture(object):
		__slots__ = ['name', 'file', 'mapping', 'extend', 'texco']

		def __init__(self, name, file, mapping, extend, texco):
			self.name    = name
			self.file    = file
			self.mapping = mapping
			self.extend  = extend
			self.texco   = texco

	def __init__(self):
		"""
		Gelato class export.
		"""

		self.PRECISION     = 6
		self.EPSILON       = 1.E-7
		self.SCALEBIAS     = 0.1
		self.FACTORAMBIENT = 200

		self.SHADOWMAP_EXT = '.sm'
		self.TEXTURE_EXT   = '.tx'
		self.DIFFUSE_EXT   = '.sdb'

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

	def generate_instance_name(self, name, ext = '', prefix = '', postfix = '', directory = True, noframe = False):
		if (directory):
			d = self.directory
		else:
			d = ''

		if (self.instance is None):
			if (noframe or self.frame is None):
				return os.path.join(d, '%s%s%s%s' % (prefix, name, postfix, ext))
			else:
				return os.path.join(d, '%s%s%s%s%s' % (prefix, name, postfix, self.pyg.mask % self.frame, ext))
		else:
			if (noframe or self.frame is None):
				return os.path.join(d, '%s%s%s-%s%s' % (prefix, name, postfix, self.instance, ext))
			else:
				return os.path.join(d, '%s%s%s-%s%s%s' % (prefix, name, postfix, self.instance, self.pyg.mask % self.frame, ext))

	def generate_split_name(self, name, prefix, i, n):
		if (self.frame is None):
			if (n <= 1):
				return '%s_%s_%s%s' % (self.base, prefix, name, self.ext)
			else:
				return '%s_%s_%s-%s%s' % (self.base, prefix, name, i, self.ext)
		else:
			if (n <= 1):
				return '%s_%s_%s%s%s' % (self.base, prefix, name, self.mask % self.frame, self.ext)
			else:
				return '%s_%s_%s-%s%s%s' % (self.base, prefix, name, i, self.mask % self.frame, self.ext)

	def object_name(self, name):
		if (self.instance is None):
			return name
		return self.generate_instance_name(name, prefix = '__', ext = '__', directory = False, noframe = True)

	def camera_shadow_name(self, name):
		return self.generate_instance_name(name, prefix = '__shadow_', ext = '__', directory = False, noframe = True)

	def file_shadow_name(self, name):
		return self.generate_instance_name(space2underscore(name), self.SHADOWMAP_EXT, self.base + '_shadow_')

	def file_diffuse_name(self, name):
		return self.generate_instance_name(space2underscore(name), self.DIFFUSE_EXT, self.base + '_diffuse_')

	def file_object_name(self, name, i, n):
		return self.generate_split_name(space2underscore(name), 'object', i, n)

	def file_output_pass(self):
		if (self.npasses <= 1):
			if (self.on_ambient_occlusion):
				return str(self.filename_ambient_occlusion)
			return str(self.filename)

		if (self.on_beauty):
			return str(self.filename_beauty)
		elif (self.on_shadows):
			return str(self.filename_shadows)
		elif (self.on_ambient_occlusion):
			return str(self.filename_ambient_occlusion)
		elif (self.on_bake_diffuse):
			return str(self.filename_bake_diffuse)

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
				wfile.write(struct.pack('=BL', self.BINARY_INT, l))
				for i in array:
					wfile.write(struct.pack('=i', i))
			elif (ty is float):
				wfile.write(struct.pack('=BL', self.BINARY_FLOAT, l))
				for f in array:
					try:
						s = struct.pack('=f', f)
					except:
						s = struct.pack('=f', 0.0)
					wfile.write(s)
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
		if (shader_environment_light):
			shader_environment_light['occlusionmap'] = output

			shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
			if (shader_ambient_occlusion):
				shader_environment_light['occlusionname'] = shader_ambient_occlusion['occlusionname']

			self.file.write(str(shader_environment_light))
		else:
			self.file.write('Light ("__envlight_pass2__", "envlight", "string occlusionmap", "%s" )\n' %
				output)

	def write_indirect_light(self):
		global lights_assign

		self.file.write('\nAttribute ("string geometryset", "+indirect")\n')
		self.file.write('Attribute ("int indirect:minsamples", %d)\n' %
			self.indirect_minsamples)

		shader_indirect_light = lights_assign[0]['indirect_light']
		if (shader_indirect_light):
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

	def nonspecular(self, lamp):
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

			if (self.enable_stereo and self.on_beauty):
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
		type = obj.type
		if (type != 'Camera'):
			return

		name	= obj.name
		matrix	= obj.getMatrix()
		cam	= Blender.Camera.Get(obj.getData().name)

		ratio_x = self.context.aspectRatioX()
		ratio_y = self.context.aspectRatioY()
		ratio	= float(ratio_y) / float(ratio_x)

		self.file.write('\nPushTransform ()\n')
		self.file.write('PushAttributes ()\n')

		# Transform

		self.write_move_scale_rotate(matrix)

		# Clipping planes

		self.file.write('Attribute ("float near", %s)\n' %
			round(cam.clipStart, self.PRECISION))

		self.file.write('Attribute ("float far", %s)\n' %
			round(cam.clipEnd, self.PRECISION))

		# Perspective camera

		if (cam.type == 'persp'):

			if (ratio_x != ratio_y):
				aspx = self.sizex / self.sizey
				aspy = ratio
				self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
					(-aspx, aspx, -aspy, aspy))

			if (self.sizex > self.sizey):
				fac = self.sizey / self.sizex
			else:
				fac = 1.0

			fov = math.degrees(2.0 * math.atan2(16.0 * fac, cam.lens))

			self.file.write('Attribute ("string projection", "perspective")\n')
			self.file.write('Attribute ("float fov", %s)\n' %
				round(fov, self.PRECISION))

		# Orthographic camera

		elif (cam.type == 'ortho'):

			aspx = cam.scale / 2.0
			aspy = aspx * self.sizey / self.sizex * ratio

			self.file.write('Attribute ("string projection", "orthographic")\n')
			self.file.write('Attribute ("float[4] screen", (%s, %s, %s, %s))\n' %
				(-aspx, aspx, -aspy, aspy))

		else:
			raise GelatoError, 'Invalid camera type "%s"' % cam.type

		self.file.write('Attribute ("float pixelaspect", %s)\n' %
			(1.0 / ratio))

		# Depth of Field

		if (self.enable_dof and self.on_beauty):
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

		# Motion Blur

		if (self.enable_motion_blur and self.on_beauty):
			self.file.write('Attribute ("int temporalquality", %s)\n' %
				self.temporalquality)

			self.file.write('Attribute ("float[2] shutter", (%s, %s))\n' %
				(self.shutter_open, self.shutter_close))

		# Stereo camera

		if (self.enable_stereo and self.on_beauty):
			self.file.write('Attribute ("float stereo:separation", %s)\n' %
				float(self.stereo_separation))

			self.file.write('Attribute ("float stereo:convergence", %s)\n' %
				float(self.stereo_convergence))

			self.file.write('Attribute ("string stereo:projection", "%s")\n' %
				self.stereo_projection)

			self.file.write('Attribute ("string stereo:shade", "%s")\n' %
				self.stereo_shade)

		# Camera

		self.file.write('Camera ("%s")\n' % name)

		self.file.write('PopAttributes ()\n')
		self.file.write('PopTransform ()\n')

	def write_camera_light(self, obj, lamp, name, matrix):
		self.file.write('\nPushTransform ()\n')

		self.write_move_scale_rotate(matrix)

		self.file.write('Camera ("%s", '
				'"int[2] resolution", (%d, %d), '
				'"int[2] spatialquality", (%d, %d), '
				'"string projection", "perspective", '
				'"float fov", %s, '
				'"float near", %s, '
				'"float far", %s)\n' % (
			self.camera_shadow_name(name),
			lamp.bufferSize, lamp.bufferSize,
			lamp.samples, lamp.samples,
			lamp.spotSize,
			lamp.clipStart,
			lamp.clipEnd))

		self.file.write('PopTransform ()\n')

		if (self.enable_dynamic):
			self.file.write('Parameter ("int dynamic", 1)\n')

		if (self.shadow_woo):
			shadow_data = 'avgz'
		else:
			shadow_data = 'z'

		self.file.write('Output ("%s", '
				'"shadow", "%s", "%s", '
				'"string compression", "%s", '
				'"string filter", "min", '
				'"float[2] filterwidth", (1.0, 1.0), '
				'"float dither", 0.0, '
				'"int[4] quantize", (0, 0, 0, 0))\n' % (
			self.file_shadow_name(name),
			shadow_data,
			self.camera_shadow_name(name),
			self.compression_shadow))

	def write_script(self, name):
		if (name is None):
			return

		try:
			txt = Blender.Text.Get(name)
		except:
			if (self.verbose > 1):
				print 'Error: invalid script "%s"' % name
			return

		if ((txt is None) or (txt.nlines == 0)):
			return

		self.file.write('\nInput ("pyg << ')

		for line in txt.asLines():
			if (line):
				self.file.write(escape_quote(line))
				self.file.write('\\n')

		self.file.write('")\n')

	def write_mesh(self, name, i, n, single_sided, interpolation, nverts,\
			verts, points, normals = [], vertexcolor = [], holes = [], s = [], t = []):

		if (single_sided):
			self.file.write('Attribute ("int twosided", 0)\n')

		if (self.enable_split):
			fobj_name = self.file_object_name(name, i, n)

			self.file.write('Input ("%s")\n' % fobj_name)

			if (fobj_name not in self.fileobject_memo):

				wfile = open(fobj_name, 'w')
				self.fileobject_memo.append(fobj_name)

				if (self.verbose > 1):
					print 'Info: exporting object file "%s"' % fobj_name
			else:
				return
		else:
			wfile = self.file

		if (self.verbose > 0):
			wfile.write('## Points: %s\n' % (len(points) / 3))
			wfile.write('## Faces:  %s\n' % len(nverts))

		wfile.write('Mesh ("%s"' % interpolation)

		self.write_array(wfile, nverts,      ',', True)
		self.write_array(wfile, verts,       ',', True)
		self.write_array(wfile, points,      ',"vertex point P",')
		self.write_array(wfile, normals,     ',"vertex normal N",')
		self.write_array(wfile, vertexcolor, ',"vertex color C",')
		self.write_array(wfile, s,           ',"linear float s",')
		self.write_array(wfile, t,           ',"linear float t",')
		self.write_array(wfile, holes,       ',"int[%d] holes",' % len(holes), True)

		wfile.write(')\n')

		if (self.enable_split):
			wfile.close()

	def camera_shadows(self, obj, matrices):
		global lights_assign

		type = obj.type
		if (type != 'Lamp'):
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

	def light(self, obj, matrices):
		global lights_assign

		type = obj.type
		if (type != 'Lamp'):
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
					print 'Info: exclude lamp "%s"' % name

	def mesh(self, obj, matrices):
		global materials_assign

		type = obj.type
		if ((type != 'Mesh') and (type != 'Surf')):
			return

		name = obj.name

		try:
			mesh = Blender.NMesh.GetRawFromObject(name)
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())
			return

		nfaces = len(mesh.faces)
		if (nfaces == 0):
			return

		# single sided face

		single_sided = False
		if (not (self.all_double_sided or (mesh.mode & Blender.NMesh.Modes.TWOSIDED))):
			single_sided = True

		# vertex colors

		vtcolor = mesh.hasVertexColours()

		# face UV

		faceuv = mesh.hasFaceUV()

		# get properties

		catmull_clark = get_property_bool(obj, 'gelato:catmull_clark')
		bake_diffuse  = get_property_bool(obj, 'gelato:bake_diffuse')

		# interpolation type

		if (catmull_clark):
			interpolation = 'catmull-clark'
		else:
			interpolation = 'linear'

		# if NURBS smooth surface

		if (type == 'Surf'):
			smooth = True
		else:
			smooth = False

		# geometry

		if (vtcolor):
			nlist_col = range(len(mesh.verts))

		nverts = []
		verts = []
		db_geometry = {}

		for i, face in enumerate(mesh.faces):
			if (face.smooth):
				smooth = True

			l = len(face.v)
			nverts.append(l)
			mat_idx = face.materialIndex

			if (db_geometry.has_key(mat_idx)):
				db_geometry[mat_idx].append(i, l)
			else:
				db_geometry[mat_idx] = self.data_geometry(i, l)

			for vert in face.v:
				verts.append(vert.index)
				db_geometry[mat_idx].append_vert(vert.index)

			if (vtcolor):
				for j in xrange(len(face.v)):
					c = face.col[j]
					nlist_col[face.v[j].index] = [c.r, c.g, c.b]

		# points

		points = []
		nlist_nor = []
		for vert in mesh.verts:
			nlist_nor.append(vert.no)
			points.extend([vert.co.x, vert.co.y, vert.co.z])

		# normals

		normals = []
		if (smooth and (not catmull_clark)):
			for face in mesh.faces:
				if (face.smooth):
					continue
				for vert in face.v:
					nlist_nor[vert.index] = face.no

			for nor in nlist_nor:
				normals.extend([nor[0], nor[1], nor[2]])

		# vertex color

		vertexcolor = []
		if (vtcolor):
			for c in nlist_col:
				try:
					vertexcolor.extend([c[0]/255.0, c[1]/255.0, c[2]/255.0])
				except:
					vertexcolor.extend([0.0, 0.0, 0.0])

		self.file.write('\nPushAttributes ()\n')

		self.file.write('Attribute ("string name", "%s")\n' %
			self.object_name(name))

		# transform

		l = len(matrices)
		if (l == 1):

			self.write_set_transform(matrices[0])

		elif (l == 2) :

			# motion blur

			self.file.write('Motion (%s, %s)\n' %
				(self.shutter_open, self.shutter_close))

			self.write_set_transform(matrices[0])
			self.write_set_transform(matrices[1])
		else:
			raise GelatoError, sys._getframe(0).f_code.co_name + ' invalid number of items'

		# bake diffuse

		if (bake_diffuse and self.on_bake_diffuse):
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

		if (mesh.materials and (not self.on_ambient_occlusion) and (not self.on_shadows)):

			# materials

			multiple_mat = len(mesh.materials) > 1
			if (multiple_mat and catmull_clark):
				set_mat = set(range(nfaces))

			ngeo = len(db_geometry)

			for i, geo in db_geometry.iteritems():

				try:
					mat = mesh.materials[i]
				except:
					continue

				if (not mat):
					continue

				self.file.write('PushAttributes ()\n')

				flags = mat.getMode()

				# vertex color

				if (not flags & Blender.Material.Modes.VCOL_PAINT):
					vertexcolor = []

				# multiple materials on a single mesh

				if (multiple_mat and catmull_clark):
					holes = list(set_mat - set(geo.materials))
				else:
					holes = []

				# color

				self.file.write('Attribute ("color C", (%s, %s, %s))\n' % (
					round(mat.R, self.PRECISION),
					round(mat.G, self.PRECISION),
					round(mat.B, self.PRECISION)))

				# alpha

				alpha = mat.alpha
				if (alpha < 1.0):
					alpha = round(alpha, self.PRECISION)
					self.file.write('Attribute ("color opacity", (%s, %s, %s))\n' %
						(alpha, alpha, alpha))

				# texture files (FIXME)

				use_uv = False
				textures_color = []
				list_tex = mat.getTextures()

				if (list_tex):
					for mtex in list_tex:
						if (not mtex):
							continue
						if (mtex.tex.type is Blender.Texture.Types.IMAGE):
							image = mtex.tex.getImage()
							if (not image):
								continue
							filename = Blender.sys.expandpath(image.getFilename())
							if (mtex.mapto & Blender.Texture.MapTo.COL):
								textures_color.append(self.data_texture(mtex.tex.getName(),
									filename,
									mtex.mapping,
									mtex.tex.extend,
									mtex.texco))
								if (mtex.texco & Blender.Texture.TexCo.UV):
									use_uv = True

				# UV coordinate

				tex_s = []
				tex_t = []

				if (self.enable_textures and use_uv and faceuv):
					for face in mesh.faces:
						for uv in face.uv:
							tex_s.append(round(      uv[0], self.PRECISION))
							tex_t.append(round(1.0 - uv[1], self.PRECISION))

				# shader surface (FIXME)

				if (self.enable_textures and textures_color and self.on_beauty):
					self.file.write('ShaderGroupBegin ()\n')

					for ftex in textures_color:
						if (self.verbose > 0):
							self.file.write('## Texture: "%s"\n' % ftex.name)
						self.file.write('Shader ("surface", "pretexture", "string texturename", "%s", "string wrap", "%s")\n' %
							(fix_file_name(ftex.file), self.convert_extend[ftex.extend]))

				if (self.verbose > 0):
					self.file.write('## Material: "%s"\n' % mat.name)

				if (self.enable_shaders and not self.enable_debug_shaders):

					if ((not flags & Blender.Material.Modes.SHADELESS) and not (bake_diffuse and self.on_bake_diffuse)):
						if (materials_assign[1].has_key(mat.name)):
							sd = copy.deepcopy(materials_assign[1][mat.name])
							if (sd is not None):
								if (bake_diffuse and self.enable_bake_diffuse and self.on_beauty and sd.widget_enable_sss.val):
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

				if (self.enable_textures and textures_color and self.on_beauty):
					self.file.write('ShaderGroupEnd ()\n')

				# FIXME MA_ONLYCAST ???
				if (flags & 0x2000):
					self.file.write('Attribute ("string geometryset", "-camera")\n')

				if (not (flags & Blender.Material.Modes.TRACEABLE)):
					self.file.write('Attribute ("string geometryset", "-shadows")\n')

				if (flags & Blender.Material.Modes.TRANSPSHADOW):
					self.file.write('Attribute ("int ray:opaqueshadows", 0)\n')

				# geometry

				if (catmull_clark):
					self.write_mesh(name, i, ngeo, single_sided, interpolation, nverts,
						verts,     points, normals, vertexcolor, holes, tex_s, tex_t)
				else:
					self.write_mesh(name, i, ngeo, single_sided, interpolation, geo.nverts,
						geo.verts, points, normals, vertexcolor, [],	tex_s, tex_t)

				self.file.write('PopAttributes ()\n')
		else:
			self.write_mesh(name, 0, 0, single_sided, interpolation, nverts, verts, points, normals)

		self.file.write('PopAttributes ()\n')

	def visible(self, obj):
		"""
		Check if object is visible
		"""

		if ((obj.users > 1) and ((frozenset(obj.layers) & self.viewlayer) == frozenset())):
			if (self.verbose > 1):
				print 'Info: Object "%s" invisible' % obj.name
			return False
		return True

	def build(self, obj, method, mblur = False):
		if (not self.visible(obj)):
			return

		self.instance = None

		mb = mblur and self.on_beauty

		if (self.dup_verts):
			try:
				# get duplicate object
				dupobjs = obj.DupObjects
			except:
				dupobjs = None

			if (dupobjs):

				self.instance = 0

				# check is motion blur
				if (mb):
					(matrix_start, matrix_end) = self.shutter_matrices(obj, True)

					for dobj, mat in dupobjs:

						matrices = self.interpolation_motion_blur(matrix_start[self.instance], \
							matrix_end[self.instance])
						exec('self.%s(dobj, matrices)' % method)

						self.instance += 1
				else:
					for dobj, mat in dupobjs:
						exec('self.%s(dobj, [mat])' % method)
						self.instance += 1
				return
			else:
				try:
					# skip object if DupObjects
					if (obj.parent and obj.parent.DupObjects):
						return
				except:
					pass

		# check is motion blur
		if (mb):
			(matrix_start, matrix_end) = self.shutter_matrices(obj)

			matrices = self.interpolation_motion_blur(matrix_start, matrix_end)
		else:
			matrices = [obj.matrix]

		exec('self.%s(obj, matrices)' % method)

	def lights_to_cameras(self):
		for obj in self.objects:
			self.build(obj, 'camera_shadows')

	def lights(self):
		global INTERACTIVE

		if (INTERACTIVE):
			bar = 'Lights ...'
			if (not ((self.frame is None) or (self.nframes is None))):
				bar += ' (%d/%d)' % (self.frame, self.nframes)
			Blender.Window.DrawProgressBar(0.0, bar)

		self.write_ambientlight()

		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):

			self.build(obj, 'light')

			if (INTERACTIVE):
				Blender.Window.DrawProgressBar(float(i) / n, bar)

	def geometries(self):
		global INTERACTIVE

		if (INTERACTIVE):
			bar = 'Geometries ...'
			if (not ((self.frame is None) or (self.nframes is None))):
				bar += ' (%d/%d)' % (self.frame, self.nframes)
			Blender.Window.DrawProgressBar(0.0, bar)

		n = float(len(self.objects))
		for i, obj in enumerate(self.objects):

			if (self.verbose > 1):
				print 'Info: Object "%s" type "%s"' % (obj.name, obj.type)

			self.build(obj, 'mesh', self.enable_motion_blur)

			if (INTERACTIVE):
				Blender.Window.DrawProgressBar(float(i) / n, bar)

	def write_head(self):
		"""
		Write pyg header.
		"""

		# get camera

		curcam = self.scene.objects.camera

		try:
			self.camera_name = curcam.name
		except:
			raise GelatoError, 'Not camera present'

		scale = self.context.getRenderWinSize() / 100.0

		# banner

		self.file.write('## Exported by Blender Gelato %s\n##\n' % __version__)
		self.file.write(datetime.datetime.today().strftime('## Timestamp: %Y-%m-%d %H:%M:%S\n'))

		if (USE_GETPASS):
			self.file.write('## User: %s\n' % getpass.getuser())

		self.file.write('## Blender: %s\n' % Blender.Get('version'))

		self.file.write('## Platform: %s\n' % sys.platform)

		if (self.on_beauty):
			pass_render = 'Beauty'
		elif (self.on_shadows):
			pass_render = 'Shadows'
		elif (self.on_ambient_occlusion):
			pass_render = 'Ambient Occlusion'
		elif (self.on_bake_diffuse):
			pass_render = 'Bake Diffuse'
		else:
			pass_render = 'Unknow'

		self.file.write('## Pass: %s\n' % pass_render)

		if (not ((self.frame is None) or (self.nframes is None))):
			self.file.write('## Frame: %d/%d\n' %
				(self.frame, self.nframes))

		# verbose

		self.file.write('\nAttribute ("int verbosity", %d)\n' %
			self.verbose)

		# error filename

		if (self.enable_error and self.errorfilename):
			self.file.write('Attribute ("string error:filename", "%s")\n' %
				fix_file_name(self.errorfilename))

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

		# resolution X Y

		self.file.write('Attribute ("int[2] resolution", (%d, %d))\n' %
			(int(self.sizex * scale), int(self.sizey * scale)))

		# border render

		if (self.context.borderRender):
			self.file.write('Attribute ("float[4] crop", (%s, %s, %s, %s))\n' % (
				self.context.border[0],
				self.context.border[2],
				1.0 - self.context.border[3],
				1.0 - self.context.border[1]))
#			self.file.write('Attribute ("int rerender", 1)\n')

		# antialiasing

		self.file.write('Attribute ("int[2] spatialquality", (%d, %d))\n' %
			(self.antialiasing_x , self.antialiasing_y))

		# preview

		if (self.enable_preview):
			self.file.write('Attribute ("float preview", %s)\n' %
				round(self.preview_quality, self.PRECISION))

		# shading

		if (self.enable_shaders):
			self.file.write('Attribute ("float shadingquality", %s)\n' %
				round(self.shadingquality, self.PRECISION))

		#  bucket

		self.file.write('Attribute ("int[2] limits:bucketsize", (%d, %d))\n' %
			(self.bucketsize_x , self.bucketsize_y))

		self.file.write('Attribute ("string bucketorder", "%s")\n' %
			self.bucketorder)

		# mesh

		self.file.write('Attribute ("string orientation", "outside")\n')
		self.file.write('Attribute ("int twosided", 1)\n')

		# textures

		if (self.enable_textures):
			self.file.write('Attribute ("int texture:automipmap", %d)\n' %
				self.enable_automipmap)

			self.file.write('Attribute ("int limits:texturememory", %d)\n' %
				int(self.limits_texturememory))

			self.file.write('Attribute ("int limits:texturefiles", %d)\n' %
				int(self.limits_texturefiles))

		# units

		self.file.write('Attribute ("float units:fps", %s)\n' %
			self.context.fps)

		if (self.units_length):
			self.file.write('Attribute ("string units:length", "%s")\n' %
				self.units_length)

			self.file.write('Attribute ("float units:lengthscale", %s)\n' %
				round(float(self.units_lengthscale), self.PRECISION))

		# ray traced

		if (self.enable_ray_traced):
			self.write_ray_traced()

		# camera/s

		self.write_camera(curcam)

#		for obj in self.objects:
#			self.write_camera(obj)

		# shadows

		if ((self.shadow_maps or self.shadow_woo) and
			((self.on_beauty and self.enable_dynamic) or self.on_shadows)):
				self.lights_to_cameras()

		if (self.on_shadows):
			self.write_device(self.title, 'null', self.data_color, self.camera_name)

		# ambient occlusion

		if (self.on_beauty or self.on_bake_diffuse or self.on_ambient_occlusion):
			if (self.enable_viewer):
				self.write_device(self.title, 'iv', self.data_color, self.camera_name)

		if (self.on_ambient_occlusion):
			if (self.format):
				self.write_device(str(self.output_ambient_occlusion), self.format, self.data_color, self.camera_name)
			elif (self.npasses > 1):
				raise GelatoError, 'No output format'

		# output device

		if (self.format and self.on_beauty):
			self.write_device(str(self.output_color), self.format, self.data_color, self.camera_name)

			if (self.data_z):
				self.write_device(str(self.output_z), self.format, self.data_z, self.camera_name)

		# script

		if (self.enable_script_header):
			self.write_script(self.script_header)

		self.file.write('\nWorld ()\n')

	def write_tail(self):
		"""
		Write the final part of pyg file.
		"""

		self.file.write('\nRender ("%s")\n\n'
			% self.camera_name)

	def sequence(self):
		fileout = self.file_output_pass()

		# open file pyg

		try:
			self.file = open(fileout, 'w')
		except IOError:
			raise GelatoError, 'Cannot write file "%s"' % fileout
		except:
			sys.excepthook(*sys.exc_info())

		# write head of the file

		self.write_head()

		# ambient_occlusion

		if (self.on_ambient_occlusion):
			self.write_ambient_occlusion_pass1()

		# beaty or bake diffuse

		if (self.on_beauty or self.on_bake_diffuse):
			if (self.enable_sky):
				self.write_background_color()

			if (self.enable_key_fill_rim):
				self.write_key_fill_rim()

			if (self.enable_lights):
				self.lights()

			if (self.shadow_ray_traced):
				self.write_shadow_ray_traced()

		# only beauty

		if (self.on_beauty):
			if (self.enable_ambient_occlusion):
				self.write_ambient_occlusion_pass2()

			if (self.enable_indirect_light):
				self.write_indirect_light()

		# debug shader

		if (self.enable_debug_shaders and gelato_gui.debug_shader is not None):
			self.file.write('\n')
			self.file.write(str(gelato_gui.debug_shader))

		# write all geometries

		self.geometries()

		# write tail of the file

		self.write_tail()

		# close file pyg

		self.file.close()

	def sequence_pass(self):
		self.fileobject_memo = []

		self.on_beauty            = False
		self.on_shadows           = False
		self.on_ambient_occlusion = False
		self.on_bake_diffuse      = False

		if (self.pass_shadows):
			self.on_shadows = True
			self.sequence()
			self.on_shadows = False

		if (self.pass_ambient_occlusion):
			self.on_ambient_occlusion = True
			self.sequence()
			self.on_ambient_occlusion = False

		if (self.pass_bake_diffuse):
			self.on_bake_diffuse = True
			self.sequence()
			self.on_bake_diffuse = False

		if (self.pass_beauty):
			self.on_beauty = True
			self.sequence()
			self.on_beauty = False

	def shutter_matrices(self, obj, dup = False):

		# get current frame

		curframe = Blender.Get('curframe')

		try:
			# shutter

			self.eval_shutter_open	= float(eval(self.shutter_open))
			self.eval_shutter_close = float(eval(self.shutter_close))

			if (self.eval_shutter_close < self.eval_shutter_open):
				raise GelatoError, 'Invalid shutter range'

			# frame open

			frame_open = math.floor(float(curframe) + self.eval_shutter_open)
			Blender.Set('curframe', int(frame_open))

			if (dup):
				matrix_start = []
				for dobj, mat in obj.DupObjects:
					matrix_start.append(mat.copy())
			else:
				matrix_start = obj.matrix.copy()

			# frame close

			frame_close = math.ceil(float(curframe) + self.eval_shutter_close)
			Blender.Set('curframe', int(frame_close))

			if (dup):
				matrix_end = []
				for dobj, mat in obj.DupObjects:
					matrix_end.append(mat.copy())
			else:
				matrix_end = obj.matrix.copy()

			self.delta_frames = frame_close - frame_open

			return [matrix_start, matrix_end]

		finally:
			# restore frame

			Blender.Set('curframe', curframe)

	def interpolation_motion_blur(self, matrix_start, matrix_end):

		# parametrics

		t_open	= clamp(self.eval_shutter_open	/ self.delta_frames, 0.0, 1.0)
		t_close = clamp(self.eval_shutter_close / self.delta_frames, 0.0, 1.0)

		# quaternions translation

		tran_start = matrix_start.translationPart()
		tran_end   = matrix_end.translationPart()

		qtran_start = Blender.Mathutils.Quaternion(0, tran_start[0], tran_start[1], tran_start[2])
		qtran_end   = Blender.Mathutils.Quaternion(0, tran_end[0],   tran_end[1],   tran_end[2])

		# quaternions rotations

		qrot_start = matrix_start.toQuat()
		qrot_end   = matrix_end.toQuat()

		# scales

		scale_start = matrix_start.scalePart()
		scale_end   = matrix_end.scalePart()

		# Spherical Linear Interpolation translations

		qtran_open  = Blender.Mathutils.Slerp(qtran_start, qtran_end, t_open)
		qtran_close = Blender.Mathutils.Slerp(qtran_start, qtran_end, t_close)

		# Spherical Linear Interpolation rotations

		qrot_open  = Blender.Mathutils.Slerp(qrot_start, qrot_end, t_open)
		qrot_close = Blender.Mathutils.Slerp(qrot_start, qrot_end, t_close)

		# Linear Interpolation scales

		scale_open  = scale_start * (1.0 - t_open)  + scale_end * t_open
		scale_close = scale_start * (1.0 - t_close) + scale_end * t_close

		# quaternions to matrices

		matrix_open = qrot_open.toMatrix().resize4x4() \
			* Blender.Mathutils.Matrix(
				[scale_open[0], 0.0,           0.0,           0.0],
				[0.0,		scale_open[1], 0.0,           0.0],
				[0.0,		0.0,           scale_open[2], 0.0],
				[qtran_open[1], qtran_open[2], qtran_open[3], 1.0])

		matrix_close = qrot_close.toMatrix().resize4x4() \
			* Blender.Mathutils.Matrix(
				[scale_close[0], 0.0,            0.0,            0.0],
				[0.0,            scale_close[1], 0.0,            0.0],
				[0.0,            0.0,            scale_close[2], 0.0],
				[qtran_close[1], qtran_close[2], qtran_close[3], 1.0])

		# matrix shutter open and close

		return [matrix_open, matrix_close]

	def write_command(self):

		# shadows

		if (self.pass_shadows):
			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, self.filename_shadows))

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
			if (self.npasses <= 1):
				name = self.filename
			else:
				name = self.filename_beauty

			self.file.write('Command ("system", "string[2] argv", ("%s", "%s"))\n' %
				(GELATO, name))

	def setup(self):
		global permanents, gelato_gui

		for name, value in permanents.iteritems():
			if (name[0] == '_'):
				setattr(self, name[1:], value.val)
			else:
				setattr(self, name, value.val)

		# filename

		self.filename = fix_file_name(self.filename)

		# compression

		comp = gelato_gui.menu_format.convert(self.format)[2]
		if (comp):
			self.compression = comp.convert(self.compression)
		else:
			self.compression = None

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

		global INTERACTIVE

		# leave edit mode before getting the mesh

		if (Blender.Window.EditMode()):
			Blender.Window.EditMode(0)

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

		self.npasses = sum([self.pass_beauty, self.pass_shadows, self.pass_ambient_occlusion, self.pass_bake_diffuse])
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

		self.filename			= self.name_mask(self, '',                   self.ext)
		self.filename_beauty		= self.name_mask(self, '_beauty',            self.ext)
		self.filename_shadows		= self.name_mask(self, '_shadows',           self.ext)
		self.filename_ambient_occlusion = self.name_mask(self, '_ambient_occlusion', self.ext)
		self.filename_bake_diffuse	= self.name_mask(self, '_bake_diffuse',      self.ext)

		if (self.suffix):
			self.output_color                = self.name_mask(self, '',                   self.suffix,	True)
			self.output_z                    = self.name_mask(self, '_z',                 self.suffix,	True)
			self.output_ambient_occlusion    = self.name_mask(self, '_ambient_occlusion', self.suffix,	True)
			self.output_ambient_occlusion_tx = self.name_mask(self, '_ambient_occlusion', self.TEXTURE_EXT, True)

		if (self.verbose > 0):
			timestart = Blender.sys.time()
			print 'Info: starting Gelato pyg export to "%s"' % self.filename

		# set verbose

		for mat in materials_assign:
			for sd in mat.itervalues():
				if (sd is not None):
					sd.verbose = self.verbose

		for lig in lights_assign:
			for sd in lig.itervalues():
				if (sd is not None):
					sd.verbose = self.verbose

		self.viewlayer = frozenset(Blender.Window.ViewLayer())

		self.objects = scene.objects

		self.world = Blender.World.GetCurrent()

		self.context = self.scene.getRenderingContext()
		self.sizex   = float(self.context.imageSizeX())
		self.sizey   = float(self.context.imageSizeY())

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
			if (INTERACTIVE):
				Blender.Window.DrawProgressBar(1.0, '')

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
		global WIN
		global materials_assign, lights_assign

		self.x0  = 10	# start cursor x
		self.y0  = 10	# start cursor y
		self.h   = 22	# height button
		self.s   = 30	# step y
		self.m   = 10	# margin button
		self.spd = 540	# space default button

		if (WIN):
			self.cmd_mask = '""%s" "%s""'
		else:
			self.cmd_mask = '"%s" "%s"&'

		self.menu_surface  = None
		self.menu_light    = None

		self.menu_material = None
		self.menu_lamp     = None
		self.menu_text     = None

		self.panels = [
			self.panel('Output',         '_panel_output', self.panel_output, 'Panel output data'),
			self.panel('Geometries',     '_panel_geometries', self.panel_geometries, 'Panel geometries'),
			self.panel('Ray traced',     '_panel_ray_traced', self.panel_ray_traced, 'Panel ray traced'),
			self.panel('Textures',       '_panel_textures', self.panel_textures, 'Panel textures'),
			self.panel('Stereo',         '_panel_stereo', self.panel_stereo, 'Panel stereo rendering'),
			self.panel('Environment',    '_panel_environment', self.panel_environment, 'Panel environment'),

			self.panel('Images',         '_panel_images', self.panel_images, 'Panel images'),
			self.panel('Shaders',        '_panel_shaders', self.panel_shaders, 'Panel shaders'),
			self.panel('Lights',         '_panel_lights', self.panel_lights, 'Panel lights'),
			self.panel('Depth of Field', '_panel_dof', self.panel_dof, 'Panel depth of field'),
			self.panel('Motion Blur',    '_panel_motion_blur', self.panel_motion_blur, 'Panel Motion Blur'),
			self.panel('Scripts',        '_panel_scripts', self.panel_scripts, 'Panel scripts'),

			self.panel('Pass',           '_panel_pass', self.panel_pass, 'Panel select passes'),
			self.panel('Shadows',        '_panel_shadows', self.panel_shadows, 'Panel select shadows type'),
			self.panel('AO',             '_panel_ambient_occlusion', self.panel_ambient_occlusion, 'Panel ambient occlusion'),
			self.panel('SSS',            '_panel_sss', self.panel_sss, 'Panel SubSurface Scattering'),
			self.panel('Indirect Light', '_panel_indirectlight', self.panel_indirect_light, 'Panel indirect light'),
		]

		# ambient occlusion shader

		sd = None
		file_name = 'ambocclude.gso'

		try:
			fd = search_file(file_name, permanents['path_shader'].val)
			if (fd):
				sd = shader(fd)
				self.ambient_occlusion_setup(sd)
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Ambient occlusion is disabled' % file_name

		materials_assign[0]['ambient_occlusion'] = sd

		# envlight shader

		sd = None
		file_name = 'envlight.gso'

		try:
			fd = search_file(file_name, permanents['path_shader'].val)
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
			fd = search_file(file_name, permanents['path_shader'].val)
			if (fd):
				sd = shader(fd, '__indirectlight__')
		except:
			sys.excepthook(*sys.exc_info())
			print 'Error: shader "%s" not found. Indirect light is disabled' % file_name

		lights_assign[0]['indirect_light'] = sd

		# bake diffuse shader

		sd = None
		file_name = 'bakediffuse.gso'

		try:
			fd = search_file(file_name, permanents['path_shader'].val)
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
			fd = search_file(name + '.gso', permanents['path_shader'].val)
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

		self.available_shader = find_files('*.gso', permanents['path_shader'].val)
		if (self.available_shader):
			list_surface = []
			list_light   = []
			for name in sorted(self.available_shader):
				fd = os.path.join(self.available_shader[name], name)
				try:
					sd = shader(fd)

					ty = sd.type

					# surface, generic

					if (ty in [sd.types.surface, sd.types.generic]):
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
			['file.${FRAME}.ext', 0],
			['file.ext.${FRAME}', 1],
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
		self.x = self.x0
		self.y = self.y0

	def inc_x(self, i = 0):
		self.x += i

	def inc_y(self, i = 0):
		self.y += i

	def line_feed(self, gap = True):
		self.x = self.x0
		if (gap):
			self.inc_y(self.s)
		else:
			self.inc_y(self.h)

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

	def draw_text(self, s, size, x = 0, y = 0):
		Blender.BGL.glRasterPos2i(self.x + x, self.y + y)
		Blender.Draw.Text(s)
		self.inc_x(size + self.m)

	def draw_string(self, s, size, length, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		permanents[name] = Blender.Draw.String(s, rid, self.x, self.y, size, self.h,
			permanents[name].val, length, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw_number(self, s, size, min, max, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		permanents[name] = Blender.Draw.Number(s, rid, self.x, self.y, size, self.h,
			permanents[name].val, min, max, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw_slider(self, s, size, min, max, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		permanents[name] = Blender.Draw.Slider(s, rid, self.x, self.y, size, self.h,
			permanents[name].val, min, max, 0, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw_button(self, s, size, func, help = '', sep = None):
		rid = self.get_id(id(func), func)
		Blender.Draw.PushButton(s, rid, self.x, self.y, size, self.h, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw_toggle(self, s, size, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		permanents[name] = Blender.Draw.Toggle(s, rid, self.x, self.y, size, self.h,
			permanents[name].val, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw_menu(self, bake, size, name, func = None, help = '', sep = None):
		rid = self.get_id(name, func)
		permanents[name] = Blender.Draw.Menu(bake.cookie, rid, self.x, self.y, size, self.h,
			permanents[name].val, help)
		if (sep is None):
			self.inc_x(size + self.m)
		else:
			self.inc_x(size + sep)
		return rid

	def draw(self):
		self.home()
		self.reset_id()

		Blender.BGL.glClearColor(.5325, .6936, .0, 1.0)
		Blender.BGL.glClear(Blender.BGL.GL_COLOR_BUFFER_BIT)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

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
		if ((not val) and (evt in [Blender.Draw.LEFTMOUSE, Blender.Draw.MIDDLEMOUSE, Blender.Draw.RIGHTMOUSE])):
			Blender.Draw.Redraw(1)
			return

		if (evt in [Blender.Draw.ESCKEY, Blender.Draw.QKEY]):
			ret = Blender.Draw.PupMenu('OK?%t|Exit Blender Gelato%x1')
			if (ret == 1):
				xml_save()
				Blender.Draw.Exit()
				return

	def handle_button_event(self, evt):
		global materials_assign, lights_assign

		if (self.id_buttons.has_key(evt)):
			func = self.id_buttons[evt]
			if (func):
				func(evt)

		# passes

		if (permanents['format'].val == self.val_format_null):
			permanents['enable_viewer'].val = 1

		if (permanents['enable_dynamic'].val or permanents['shadow_ray_traced'].val):
			permanents['pass_shadows'].val = 0

		if (not permanents['enable_ambient_occlusion'].val):
			permanents['pass_ambient_occlusion'].val = 0

		if (not permanents['enable_bake_diffuse'].val):
			permanents['pass_bake_diffuse'].val = 0

		if (not (permanents['pass_beauty'].val or
			permanents['pass_shadows'].val or
			permanents['pass_ambient_occlusion'].val or
			permanents['pass_bake_diffuse'].val)):
				permanents['pass_beauty'].val = 1

		# filters

		if ((permanents['data'].val < self.val_data_z) and
			(permanents['filter'].val >= self.val_filter_min)):
				permanents['filter'].val = 0 # Gaussian

		# materials

		for sd in materials_assign[0].itervalues():
			if (sd is not None):
				sd.update(evt)

		if (self.menu_material):
			material_name = self.menu_material.convert(permanents['_select_material'].val)
			if (materials_assign[1].has_key(material_name) and (materials_assign[1][material_name] is not None)):
				materials_assign[1][material_name].update(evt)

		if ((permanents['_enable_debug_shaders'].val) and (self.debug_shader is not None)):
			self.debug_shader.update(evt)

		# lights

		for sd in lights_assign[0].itervalues():
			if (sd is not None):
				sd.update(evt)

		if (self.menu_lamp):
			lamp_name = self.menu_lamp.convert(permanents['_select_lamp'].val)
			if (lights_assign[1].has_key(lamp_name) and (lights_assign[1][lamp_name] is not None)):
				lights_assign[1][lamp_name].update(evt)

		# xml save

		xml_save()

		# redraw

		Blender.Draw.Redraw(1)

	def cb_exit(self, id):
		self.handle_event(Blender.Draw.ESCKEY, 0)

	def cb_default(self, id):
		ret = Blender.Draw.PupMenu('All items to default values ?%t|no%x1|yes%x2')
		if (ret != 2):
			return
		default_value()

	def cb_save(self, id):
		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

		except GelatoError, strerror:
			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_render(self, id):
		global GELATO, permanents

		try:
			# export scene

			pyg.export(Blender.Scene.GetCurrent())

			# run gelato

			if (os.path.isfile(permanents['filename'].val)):
				os.system(self.cmd_mask % (GELATO, permanents['filename'].val))

		except GelatoError, strerror:
			sys.excepthook(*sys.exc_info())
			Blender.Draw.PupMenu('Error%t|"' + str(strerror) + '"')

	def cb_menu_text(self, id):
		global permanents

		permanents['script_header'] = Blender.Draw.Create(self.menu_text.convert(permanents['_select_script_header'].val))

	def cb_script_start_remove(self, id):
		global permanents

		permanents['script_header'] = Blender.Draw.Create('')

	def cb_assign_material(self, id):
		global permanents, materials_assign

		material_name = self.menu_material.convert(permanents['_select_material'].val)
		sd = self.menu_surface.convert(permanents['_select_surface'].val)

		if (sd is not None):
			# copy object no reference
			materials_assign[1][material_name] = copy.deepcopy(sd)

	def cb_assign_light(self, id):
		global permanents, lights_assign

		lamp_name = self.menu_lamp.convert(permanents['_select_lamp'].val)
		sd = self.menu_light.convert(permanents['_select_light'].val)

		if (sd is not None):
			# copy object no reference
			lights_assign[1][lamp_name] = copy.deepcopy(sd)

	def cb_remove_material(self, id):
		global permanents, materials_assign

		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		try:
			material_name = self.menu_material.convert(permanents['_select_material'].val)
			del materials_assign[1][material_name]
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_remove_light(self, id):
		global permanents, lights_assign

		ret = Blender.Draw.PupMenu('Remove assign ?%t|no%x1|yes%x2')
		if (ret != 2):
			return

		try:
			lamp_name = self.menu_lamp.convert(permanents['_select_lamp'].val)
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
		global permanents, materials_assign

		material_name = self.menu_material.convert(permanents['_select_material'].val)
		try:
			materials_assign[1][material_name].default()
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_light_default(self, id):
		global permanents, lights_assign

		lamp_name = self.menu_lamp.convert(permanents['_select_lamp'].val)
		try:
			lights_assign[1][lamp_name].default()
		except:
			if (self.verbose > 0):
				sys.excepthook(*sys.exc_info())

	def cb_debug_shader(self, id):
		global permanents
		sd = self.menu_debug_shader.convert(permanents['_select_debug_shader'].val)
		if (sd is not None):
			if ((self.debug_shader is not None) and (self.debug_shader is sd)):
				return
			self.debug_shader = sd

	def cb_ambient_occlusion_default(self, id):
		global materials_assign
		shader_ambient_occlusion = materials_assign[0]['ambient_occlusion']
		shader_ambient_occlusion.default()
		self.ambient_occlusion_setup(shader_ambient_occlusion)

	def cb_shader_envlight_default(self, id):
		global lights_assign
		shader_environment_light = lights_assign[0]['environment_light']
		shader_environment_light.default()
		self.occlusionmap_setup(shader_environment_light)

	def cb_shader_indirect_light_default(self, id):
		global lights_assign
		lights_assign[0]['indirect_light'].default()

	def cb_shader_bake_diffuse_default(self, id):
		global materials_assign
		materials_assign[0]['bake_diffuse'].default()

	def cb_catmull_clark(self, id):
		set_property_bool('gelato:catmull_clark')

	def cb_bake_diffuse(self, id):
		set_property_bool('gelato:bake_diffuse')

	def cb_shadows(self, id):
		if (id != self.id_shadow_maps):
			permanents['shadow_maps'].val = 0
		if (id != self.id_shadow_woo):
			permanents['shadow_woo'].val = 0
		if (id != self.id_shadow_raytraced):
			permanents['shadow_ray_traced'].val = 0

	def cb_panel(self, id):
		for pan in self.panels:
			if (pan.id != id):
				permanents[pan.reg_name].val = 0

	def cb_select(self, name):
		global permanents

		permanents['filename'].val = os.path.abspath(name)

	def cb_errorselect(self, name):
		global permanents

		permanents['errorfilename'].val = os.path.abspath(name)

	def cb_filename(self, id):
		global permanents

		Blender.Window.FileSelector(self.cb_select, '.pyg', permanents['filename'].val)

	def cb_errorfilename(self, id):
		global permanents

		Blender.Window.FileSelector(self.cb_errorselect, '.txt', permanents['errorfilename'].val)

	def panel_common(self):
		self.draw_text('Blender Gelato v' + __version__, 130, 2, 6)

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

		for pan in self.panels:
			if (permanents[pan.reg_name].val):
				func = pan.func
				break
		else:
			permanents[self.panels[0].reg_name].val = 1
			func = self.panels[0].func

		for i, pan in enumerate(self.panels):
			pan.id = self.draw_toggle(pan.name, 100, pan.reg_name, self.cb_panel, pan.help)

			if ((i % 6) == 5):
				self.line_feed()

		self.line_feed()

		Blender.BGL.glColor3f(0.2, 0.2, 0.2)
		self.draw_rect(2, 2, 650, 11, False)
		Blender.BGL.glColor3f(.2392, .3098, 1.0)
		self.draw_rect(0, 4, 650, 10)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		self.line_feed()

		func()

	def panel_output(self):
		self.draw_toggle('Viewer', 100, 'enable_viewer',
			help = 'Enable window viewer')

		self.draw_toggle('Split', 100, 'enable_split',
			help = 'Split out objects into separate files')

		self.draw_toggle('Binary', 100, 'enable_binary',
			help = 'Enable binary file')

		self.draw_toggle('Anim', 100, 'enable_anim',
			help = 'Enable sequence render')

		if (permanents['enable_anim'].val):
			self.draw_menu(self.menu_files_extensions, 125, 'files_extensions',
				help = 'Templates files extensions')

		self.line_feed()

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		self.draw_text('Bucket size', 100, 2, 6)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

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

		self.draw_toggle('Preview', 100, 'enable_preview',
			help = 'Enable preview')

		if (permanents['enable_preview'].val):
			self.draw_slider('Preview quality: ', 320, 0.0, 1.0, 'preview_quality',
				help = 'Preview quality')

		self.line_feed()

		self.draw_toggle('Enable error', 100, 'enable_error',
			help = 'Enable error file')

		if (permanents['enable_error'].val):
			self.draw_button('Error file:', 100, self.cb_errorfilename,
				'Select log file', 0)

			self.draw_string('', 440, 200, 'errorfilename',
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
		self.draw_menu(self.menu_data, 105, 'data',
			help = 'Output data')

		self.draw_menu(self.menu_format, 105, 'format',
			help = 'Output format')

		(comp, comp_help) = self.menu_format.convert(permanents['format'].val)[2:4]
		if (comp):
			self.draw_menu(comp, 105, 'compression',
				help = comp_help)

		self.line_feed()

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		self.draw_text('Spatial antialiasing', 105, 2, 6)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		l = 90
		v_min = 1
		v_max = 32

		self.draw_number('X: ', l, v_min, v_max, 'antialiasing_x',
			help = 'Spatial antialiasing X', sep = 0)

		self.draw_number('Y: ', l, v_min, v_max, 'antialiasing_y',
			help = 'Spatial antialiasing Y')

		self.draw_number('Gain: ', 105, 0.0, 16.0, 'gain',
			help = 'Image gain')

		self.draw_number('Gamma: ', 105, 0.0, 16.0, 'gamma',
			help = 'Image gamma')

		self.line_feed()

		Blender.BGL.glColor3f(0.0, 0.0, 0.0)
		self.draw_text('Pixel filter width', 105, 2, 6)
		Blender.BGL.glColor3f(1.0, 1.0, 1.0)

		l = 90
		v_min = 0.0
		v_max = 32.0

		self.draw_number('X: ', l, v_min, v_max, 'filterwidth_x',
			help = 'Pixel filter width X', sep = 0)

		self.draw_number('Y: ', l, v_min, v_max, 'filterwidth_y',
			help = 'Pixel filter width Y')

		if (permanents['data'].val < self.val_data_z):
			menu_filter = self.menu_filter1
		else:
			menu_filter = self.menu_filter2

		self.draw_menu(menu_filter, 130, 'filter',
			help = 'Pixel filter')

		self.line_feed()

		v = permanents['format'].val
		if ((v != self.val_format_null) and (v != self.val_format_openEXR)):

			Blender.BGL.glColor3f(0.0, 0.0, 0.0)
			self.draw_text('Quantize', 50, 2, 6)
			Blender.BGL.glColor3f(1.0, 1.0, 1.0)

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
		self.draw_toggle('Beauty', 130, 'pass_beauty',
			help = 'Enable beauty pass')

		if ((not permanents['enable_dynamic'].val) and
			(permanents['shadow_maps'].val or permanents['shadow_woo'].val)):
				self.line_feed(False)
				self.draw_toggle('Shadows', 130, 'pass_shadows',
					help = 'Enable shadows pass')

		if (permanents['enable_ambient_occlusion'].val):
			self.line_feed(False)
			self.draw_toggle('Ambient Occlusion', 130, 'pass_ambient_occlusion',
				help = 'Enable ambient occlusion pass')

		if (permanents['enable_bake_diffuse'].val):
			self.line_feed(False)
			self.draw_toggle('Bake diffuse', 130, 'pass_bake_diffuse',
				help = 'Enable bake diffuse pass')

	def panel_geometries(self):
		self.draw_toggle('All double sided', 130, 'all_double_sided',
			help = 'Enable all double sided faces')

		self.draw_toggle('DupliVerts', 130, 'dup_verts',
			help = 'Enable DupliVerts')

		self.line_feed()

		self.draw_button('Catmull Clark', 130,
			self.cb_catmull_clark, 'Enable catmull-clark property of all selected objects')

		self.draw_button('Bake diffuse', 130,
			self.cb_bake_diffuse, 'Enable bake diffuse property of all selected objects')

	def panel_textures(self):
		self.draw_toggle('Enable', 100, 'enable_textures',
			help = 'Enable all textures')

		if (permanents['enable_textures'].val):
			self.draw_toggle('Automipmap', 100, 'enable_automipmap',
				help = 'Automatically generate mipmaps')

			self.line_feed()

			self.draw_string('Texture memory: ', 210, 30, 'limits_texturememory',
				help = 'Maximum texture cache size in kB')

			self.line_feed()

			self.draw_string('Texture files: ', 210, 30, 'limits_texturefiles',
				help = 'Maximum number of open texture file')

	def panel_shadows(self):
		self.id_shadow_maps = self.draw_toggle('Maps', 105, 'shadow_maps',
			self.cb_shadows, 'Enable shadow maps', sep = 0)

		self.id_shadow_woo = self.draw_toggle('Woo', 105, 'shadow_woo',
			self.cb_shadows, 'Enable Woo (average) shadow')

		self.id_shadow_raytraced = self.draw_toggle('Ray traced', 100, 'shadow_ray_traced',
			self.cb_shadows, 'Enable ray traced shadows')

		if (permanents['shadow_maps'].val or permanents['shadow_woo'].val):
			self.line_feed(False)

			self.draw_toggle('Dynamics', 210, 'enable_dynamic',
				help = 'Enable dynamic shadow')

			if (not permanents['enable_dynamic'].val):
				self.line_feed()

				self.draw_menu(self.menu_compression_tiff, 100, 'compression_shadow',
					help = 'Shadow compression')

	def panel_lights(self):
		self.draw_toggle('Enable', 100, 'enable_lights',
			help = 'Enable all lights')

		self.draw_toggle('Key Fill Rim', 100, 'enable_key_fill_rim',
			help = 'Enable Key Fill Rim 3-lights')

		if (permanents['enable_lights'].val):
			self.draw_slider('Lights factor: ', 320, 0.0, 1000.0, 'lights_factor',
				help = 'Lights factor')

			if (self.menu_light):

				# get all lights

				lights = Blender.Lamp.Get()
				if (lights):
					self.line_feed()

					self.menu_lamp = self.bake_menu('Lamps',
						[[l.name, l.name] for l in sorted(lights)])

					self.draw_menu(self.menu_lamp, 100, '_select_lamp',
						help = 'Select lamp')

					lamp_name = self.menu_lamp.convert(permanents['_select_lamp'].val)
					if (lights_assign[1].has_key(lamp_name)):

						l = lights_assign[1][lamp_name]

						self.draw_button('Remove', 100,
							self.cb_remove_light, 'Remove light')

						if (permanents['shadow_maps'].val or
							permanents['shadow_woo'].val or
							permanents['shadow_ray_traced'].val):

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

	def panel_shaders(self):
		global materials_assign

		self.draw_toggle('Enable', 100, 'enable_shaders',
			help = 'Enable all shaders')

		if (permanents['enable_shaders'].val):

			self.draw_number('Shading quality: ', 160, 0.0, 16.0, 'shadingquality',
				help = 'Shading quality')

			self.line_feed()

			self.draw_toggle('Enable debug', 100, '_enable_debug_shaders',
				help = 'Enable debug shaders')

			if (permanents['_enable_debug_shaders'].val):

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
					if (materials):
						self.menu_material = self.bake_menu('Materials',
							[[m.name, m.name] for m in sorted(materials)])

						self.draw_menu(self.menu_material, 100, '_select_material',
							help = 'Select material')

						material_name = self.menu_material.convert(permanents['_select_material'].val)
						if (materials_assign[1].has_key(material_name)):

							m = materials_assign[1][material_name]

							self.draw_button('Remove', 100,
								self.cb_remove_material, 'Remove material')

							if (permanents['enable_bake_diffuse'].val):

								self.line_feed()
								y = m.gui_sss(self.x, self.y, self.h, self.s)


							self.line_feed()

							y = m.gui(self.x, self.y, self.h, self.s)

							self.blank(self.spd)

							self.draw_button('Default', 100,
								self.cb_material_default, 'Default values')

							self.y = y
						else:
							self.draw_button('Assign', 100,
								self.cb_assign_material, 'Assign material')

							self.draw_menu(self.menu_surface, 100, '_select_surface',
								self.cb_menu_surface, 'Select shader')

	def panel_dof(self):
		self.draw_toggle('Enable', 100, 'enable_dof', help = 'Enable Depth Of Field')

		if (permanents['enable_dof'].val):
			self.draw_string('F/Stop: ', 100, 20, 'fstop',
				help = 'F/Stop for depth of field')

			self.draw_string('Focal length: ', 160, 20, 'focallength',
				help = 'Lens focal length')

			self.draw_number('Quality: ', 100, 1, 256, 'dofquality',
				help = 'Number of lens values for DoF')

	def panel_environment(self):
		self.draw_toggle('Sky', 60, 'enable_sky',
			help = 'Enable background color')

		self.draw_menu(self.menu_units, 100, 'units_length',
			help = 'Physical length units of "common" space')

		if (permanents['units_length'].val):
			self.draw_string('Length scale: ', 140, 20, 'units_lengthscale',
				help = 'Length unit scale of "common" space units')

	def panel_ambient_occlusion(self):
		global materials_assign

		self.draw_toggle('Enable', 100, 'enable_ambient_occlusion',
			help = 'Enable ambient occlusion')

		if (permanents['enable_ambient_occlusion'].val):

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
		global permanents, lights_assign

		self.draw_toggle('Enable', 100, 'enable_indirect_light',
			help = 'Enable indirect light')

		if (permanents['enable_indirect_light'].val):
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
		self.draw_toggle('Enable', 100, 'enable_ray_traced',
			help = 'Enable ray traced reflections and refractions')

		if (permanents['enable_ray_traced'].val):

			self.draw_toggle('Opaque shadows', 120, 'ray_traced_opaque_shadows',
				help = 'Enable objects opaque regardless of their shaders')

			if (permanents['shadow_ray_traced'].val):
				self.draw_number('Shadow bias: ', 140, 0, 16, 'ray_traced_shadow_bias',
					help = 'Ray traced shadow bias')

			self.draw_number('Raytraced max depth: ', 170, 0, 16, 'ray_traced_max_depth',
				help = 'Ray traced max depth')

	def panel_sss(self):
		self.draw_toggle('Enable', 100, 'enable_bake_diffuse',
			help = 'Enable bake diffuse')

		if (permanents['enable_bake_diffuse'].val):
			shader_bake_diffuse = materials_assign[0]['bake_diffuse']
			if (shader_bake_diffuse is not None):
				self.line_feed()

				y = shader_bake_diffuse.gui(self.x, self.y, self.h, self.s)

				self.blank(self.spd)

				self.draw_button('Default', 100, self.cb_shader_bake_diffuse_default,
					'Bake diffuse default values')

				self.y = y

	def panel_scripts(self):
		self.draw_toggle('Script header', 100, 'enable_script_header',
			help = 'Enable script header')

		if (permanents['enable_script_header'].val):
			l = 100
			script = permanents['script_header'].val
			if (script):
				self.draw_button('Remove', 100,
					self.cb_script_start_remove, 'Remove script header')

				self.draw_text(script, l, 2, 6)
			else:
				texts = Blender.Text.Get()
				if (texts):
					self.menu_text = self.bake_menu('Load script from text',
						[[t.name, t.name] for t in texts])

					self.draw_menu(self.menu_text, l, '_select_script_header',
						self.cb_menu_text, 'Select script header')

	def panel_stereo(self):
		self.draw_toggle('Enable', 100, 'enable_stereo',
			help = 'Enable stereo rendering')

		if (permanents['enable_stereo'].val):
			self.draw_menu(self.menu_stereo_projection, 100, 'stereo_projection',
				help = 'Projection for stereo cameras')

			self.draw_menu(self.menu_stereo_shade, 100, 'stereo_shade',
				help = 'Which view to shade for stereo cameras')

			self.draw_string('Separation: ', 155, 20, 'stereo_separation',
				help = 'Camera separation for stereo cameras')

			self.draw_string('Convergence: ', 155, 20, 'stereo_convergence',
				help = 'Convergence distance for stereo cameras')

	def panel_motion_blur(self):
		self.draw_toggle('Enable', 100, 'enable_motion_blur',
			help = 'Enable motion blur')

		if (permanents['enable_motion_blur'].val):
			self.draw_string('Shutter open: ', 160, 20, 'shutter_open',
				help = 'Shutter open time for motion blur')

			self.draw_string('Shutter close: ', 160, 20, 'shutter_close',
				help = 'Shutter close time for motion blur')

			self.draw_number('Quality: ', 100, 1, 256, 'temporalquality',
				help = 'Number of time values for motion blur')

# property

def set_property_bool(name):
	for obj in Blender.Object.GetSelected():
		ty = obj.type
		if ((ty != 'Mesh') and (ty != 'Surf')):
			continue
		try:
			try:
				prop = obj.getProperty(name)
				obj.removeProperty(prop)
			except:
				pass

			obj.addProperty(name, 1, 'BOOL')
			Blender.Redraw()

			Blender.Window.RedrawAll()

		except:
			sys.excepthook(*sys.exc_info())

def get_property_bool(obj, name):
	try:
		prop = obj.getProperty(name)
		if (prop.type == 'BOOL'):
			return prop.getData()
	except:
		pass

	return False

# XML data

def default_value():
	global permanents, FILENAME_PYG, WIN

	path_shader    = ':'.join(['.', os.path.join('$GELATOHOME', 'shaders'),  '&'])
	path_texture   = ':'.join(['.', os.path.join('$GELATOHOME', 'textures'), '&'])
	path_inputs    = ':'.join(['.', os.path.join('$GELATOHOME', 'inputs'),   '&'])
	path_imageio   = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])
	path_generator = ':'.join(['.', os.path.join('$GELATOHOME', 'lib'),      '&'])

	if (WIN):
		texturefiles = '100'
	else:
		texturefiles = '1000'

	permanents = {
		'filename':			Blender.Draw.Create(FILENAME_PYG),

		'enable_anim':			Blender.Draw.Create(0),
		'files_extensions':		Blender.Draw.Create(0),		# file.NNN.ext

		'enable_binary':		Blender.Draw.Create(1),

		'enable_split':			Blender.Draw.Create(0),

		'enable_script_header':		Blender.Draw.Create(0),
		'script_header':		Blender.Draw.Create(''),
		'_select_script_header':	Blender.Draw.Create(0),

		'bucketorder':			Blender.Draw.Create(2),		# Spiral
		'bucketsize_x':			Blender.Draw.Create(32),
		'bucketsize_y':			Blender.Draw.Create(32),

		'enable_error':			Blender.Draw.Create(0),
		'errorfilename':		Blender.Draw.Create('>>gelato_log.txt'),

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
		'dup_verts':			Blender.Draw.Create(1),

		'enable_ray_traced':		Blender.Draw.Create(0),
		'ray_traced_max_depth':		Blender.Draw.Create(1),
		'ray_traced_shadow_bias':	Blender.Draw.Create(0.01),
		'ray_traced_opaque_shadows':	Blender.Draw.Create(1),

		'lights_factor':		Blender.Draw.Create(50.0),
		'enable_key_fill_rim':		Blender.Draw.Create(0),
		'enable_lights':		Blender.Draw.Create(1),
		'_select_lamp':			Blender.Draw.Create(0),
		'_select_light':		Blender.Draw.Create(0),

		'enable_shaders':		Blender.Draw.Create(1),
		'shadingquality':		Blender.Draw.Create(1.0),
		'_enable_debug_shaders':	Blender.Draw.Create(0),
		'_select_debug_shader':		Blender.Draw.Create(0),
		'_select_material':		Blender.Draw.Create(0),
		'_select_surface':		Blender.Draw.Create(0),

		'enable_ambient_occlusion':	Blender.Draw.Create(0),

		'enable_bake_diffuse':		Blender.Draw.Create(0),

		'enable_indirect_light':	Blender.Draw.Create(0),
		'indirect_minsamples':		Blender.Draw.Create(3),

		'enable_textures':		Blender.Draw.Create(1),
		'enable_automipmap':		Blender.Draw.Create(1),

		'enable_dof':			Blender.Draw.Create(0),
		'fstop':			Blender.Draw.Create('4.0'),
		'focallength':			Blender.Draw.Create('0.032'),
		'dofquality':			Blender.Draw.Create(16),

		'enable_sky':			Blender.Draw.Create(1),
		'units_length':			Blender.Draw.Create(0),
		'units_lengthscale':		Blender.Draw.Create('1.0'),

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
		'pass_bake_diffuse':		Blender.Draw.Create(0),

		'enable_stereo':		Blender.Draw.Create(0),
		'stereo_separation':		Blender.Draw.Create('0'),
		'stereo_convergence':		Blender.Draw.Create('0'),
		'stereo_projection':		Blender.Draw.Create(0),		# off-axis
		'stereo_shade':			Blender.Draw.Create(1),		# center

		'enable_motion_blur':		Blender.Draw.Create(0),
		'temporalquality':		Blender.Draw.Create(16),
		'shutter_open':			Blender.Draw.Create('0.0'),
		'shutter_close':		Blender.Draw.Create('0.5'),

		'_panel_output':		Blender.Draw.Create(1),
		'_panel_images':		Blender.Draw.Create(0),
		'_panel_pass':			Blender.Draw.Create(0),
		'_panel_ambient_occlusion':	Blender.Draw.Create(0),
		'_panel_geometries':		Blender.Draw.Create(0),
		'_panel_lights':		Blender.Draw.Create(0),
		'_panel_shadows':		Blender.Draw.Create(0),
		'_panel_textures':		Blender.Draw.Create(0),
		'_panel_shaders':		Blender.Draw.Create(0),
		'_panel_dof':			Blender.Draw.Create(0),
		'_panel_environment':		Blender.Draw.Create(0),
		'_panel_indirectlight':		Blender.Draw.Create(0),
		'_panel_ray_traced':		Blender.Draw.Create(0),
		'_panel_sss':			Blender.Draw.Create(0),
		'_panel_scripts':		Blender.Draw.Create(0),
		'_panel_stereo':		Blender.Draw.Create(0),
		'_panel_motion_blur':		Blender.Draw.Create(0),
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
	global permanents

	try:
		(base, ext) = os.path.splitext(permanents['filename'].val)
	except:
		base = 'gelato'

	return	fix_file_name(base + '.xml')

def xml_save():
	global ROOT_ELEMENT, USE_XML_DOM_EXT
	global materials_assign, lights_assign
	global permanents

	# write xml file

	dom = xml.dom.minidom.getDOMImplementation()
	doctype = dom.createDocumentType(ROOT_ELEMENT, None, None)

	doc = dom.createDocument(None, ROOT_ELEMENT, doctype )

	root = doc.documentElement
	doc.appendChild(root)

	root.setAttribute('version', __version__)
	root.setAttribute('timestamp', datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S'))

	if (USE_GETPASS):
		root.setAttribute('user', getpass.getuser())

	root.setAttribute('blender', str(Blender.Get('version')))

	root.setAttribute('platform', sys.platform)

	head = doc.createElement('config')
	root.appendChild(head)

	for name in sorted(permanents.iterkeys()):
		# skip internal's names
		if (name[0] == '_'):
			continue

		elem = doc.createElement(name)
		head.appendChild(elem)
		elem.appendChild(doc.createTextNode(str(permanents[name].val).strip()))

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

	filename_xml = output_filename_xml()

	try:
		fxml = open_temp_rename(filename_xml, 'w')

	except IOError:

		print 'Error: Cannot write file "%s"' % filename_xml
		return

	except:
		sys.excepthook(*sys.exc_info())
		return

	if (USE_XML_DOM_EXT):
		xml.dom.ext.PrettyPrint(doc, fxml.fd)
	else:
		doc.writexml(fxml.fd, addindent = '  ', newl = '\n')

def xml_load():
	global ROOT_ELEMENT
	global materials_assign, lights_assign
	global permanents

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
		for name in permanents.keys():
			# skip internal's names
			if (name[0] == '_'):
				continue

			el = head[0].getElementsByTagName(name)
			if (len(el) == 0):
				continue

			el[0].normalize()
			nd = el[0].firstChild
			if (nd.nodeType != xml.dom.Node.TEXT_NODE):
				continue

			try:
				ty = type(permanents[name].val)
				if (ty is int):
					permanents[name] = Blender.Draw.Create(int(nd.data))
				elif (ty is float):
					permanents[name] = Blender.Draw.Create(float(nd.data))
				elif (ty is str):
					permanents[name] = Blender.Draw.Create(nd.data.strip())
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

def escape_quote(name):
	# replace '"' to '\"'
	return name.replace('"', '\\"')

def space2underscore(name):
	# replace spaces to '_'
	return re.sub('\s+', '_', name)

def fix_file_name(name):
	if (os.path.sep == '\\'):
		# replace '\' to '\\'
		return name.replace('\\', '\\\\')
	return name

def fix_vars(name):
	global WIN

	if (WIN):
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
	global GELATO, GSOINFO, MAKETX, WIN
	global materials_assign, lights_assign
	global permanents, gelato_gui, pyg

	PYTHON_MAJOR = 2
	PYTHON_MINOR = 4

	if (sys.version_info < (PYTHON_MAJOR, PYTHON_MINOR)):
		raise ('Error: Python version %d.%d or greater is required\nPython version is %s' % (PYTHON_MAJOR, PYTHON_MINOR, sys.version))

	ROOT_ELEMENT = 'BlenderGelato'

	# blender's mode

	INTERACTIVE = Blender.mode == 'interactive'

	# programs

	GELATO	= 'gelato'
	GSOINFO = 'gsoinfo'
	MAKETX	= 'maketx'

	if (sys.platform[:3] == 'win'):
		WIN = True
		exe = '.exe'
		GELATO	+= exe
		GSOINFO += exe
		MAKETX	+= exe
	else:
		WIN = False

	gelatohome = os.getenv('GELATOHOME')
	if (gelatohome):
		print 'Info: GELATOHOME = "%s"' % gelatohome

		GELATO	= fix_file_name(os.path.join(gelatohome, 'bin', GELATO))
		GSOINFO = fix_file_name(os.path.join(gelatohome, 'bin', GSOINFO))
		MAKETX	= fix_file_name(os.path.join(gelatohome, 'bin', MAKETX))
	else:
		print 'info: GELATOHOME environment variable not set.'

	# file name

	base = ''
	try:
		blend_file_name = Blender.Get('filename')
		(base, ext) = os.path.splitext(blend_file_name)
		if (ext.lower() == '.gz'):
			(base, ext) = os.path.splitext(base)
	except:
		pass

	if len(base) == 0:
		base = 'gelato'

	FILENAME_PYG = base + '.pyg'

	# materials and lights

	materials_assign = [{}, {}]
	lights_assign    = [{}, {}]

	# default value

	default_value()

	# gelato convert

	pyg = gelato_pyg()

	# GUI

	gelato_gui = cfggui()

	# load and save xml file

	xml_load()
	xml_save()

	# start

	if (INTERACTIVE):
		# display GUI
		Blender.Draw.Register(gelato_gui.draw, gelato_gui.handle_event, gelato_gui.handle_button_event)
	else:
		# export scene
		gelato_gui.cb_save(0)

		# export scene and run gelato
#		gelato_gui.cb_render(0)

if __name__ == '__main__':
	try:
		import psyco
		psyco.full()
#		psyco.log()
#		psyco.profile()
	except:
		pass

	main()

