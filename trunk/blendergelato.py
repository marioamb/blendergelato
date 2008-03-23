import Blender
from math import pi

VERBOSE  = 2
FILENAME = '/tmp/output.pyg'

class gelato_pyg:
   def __init__(self, filename, verbose = 1):
      self.verbose     = verbose
      self.filename    = filename
      self.LIGHTFACTOR = 100

      try:
         self.file = open(filename, 'w')

      except IOError:
                   if (self.verbose > 0) : print 'Error: cannot write file', filename

   def head(self):
      curcam  = scene.getCurrentCamera()
      camera  = Blender.Camera.Get(curcam.getData().name)
      context = scene.getRenderingContext()
      matrix  = curcam.getInverseMatrix()

      self.file.write('Output ("file.tiff", "iv", "rgba", "main")\n\n')
      self.file.write('Attribute ("int[2] resolution", (%s, %s))\n' %
         (context.imageSizeX(), context.imageSizeY()))

      self.file.write('Attribute ("float pixelaspect", %f)\n' % (float(context.aspectRatioX()) / float(context.aspectRatioY())))
      self.file.write('Attribute ("string projection", "perspective")\n')
      self.file.write('Attribute ("float fov", %f)\n' % camera.lens)

      self.file.write('AppendTransform (%f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f)\n' %
         (matrix[0][0], matrix[0][1], -matrix[0][2], matrix[0][3],
          matrix[1][0], matrix[1][1], -matrix[1][2], matrix[1][3],
          matrix[2][0], matrix[2][1], -matrix[2][2], matrix[2][3],
          matrix[3][0], matrix[3][1], -matrix[3][2], matrix[3][3]))

      self.file.write('World ()\n')

   def tail(self):
      self.file.write('\nRender ("camera")\n')

   def translate(self, obj):
      w = obj.matrix[3][3]
      if (w == 0.0):
         return
      self.file.write('Translate (%f, %f, %f)\n' %
         (obj.matrix[3][0] / w,
          obj.matrix[3][1] / w,
          obj.matrix[3][2] / w))

   def mesh(self, obj):
      name = obj.name
      mesh = Blender.NMesh.GetRawFromObject(name)

      if len(mesh.faces) == 0:
         return

      self.file.write('\nPushAttributes ()\n')
      self.file.write('PushTransform ()\n')
      self.file.write('Attribute ("string name", "%s")\n' % name)
      self.file.write('Shader ("surface", "plastic" )\n')
      self.translate(obj)

      self.file.write('Mesh ("linear", (')

      nlist = []
      for face in mesh.faces:
         nlist.append(str(len(face.v)))
      self.file.write(', '.join(nlist))

      self.file.write('), (',)

      nlist = []
      for face in mesh.faces:
                   for vert in face.v:
                           nlist.append(str(vert.index))
      self.file.write(', '.join(nlist))

      self.file.write('), "vertex point P", (',)

      nlist = []
      for vert in mesh.verts:
         nlist.append('%f, %f, %f' %
            (round(vert.co[0], 5),
             round(vert.co[1], 5),
             round(vert.co[2], 5)))
      self.file.write(', '.join(nlist))

      self.file.write('))\n')
      self.file.write('PopTransform ()\n')
      self.file.write('PopAttributes ()\n')

   def ambientlight(self):
      world = Blender.World.GetCurrent()
      if (world and (world.getAmb() != [0.0, 0.0, 0.0])):
         self.file.write('\nLight ("%s", "ambientlight", "float intensity", %f, "color lightcolor", (%f, %f, %f))\n' %
            (world.getName(), world.getRange(), world.amb[0], world.amb[1], world.amb[2]))

   def pointlight(self, lamp, name):
      self.file.write('Light ("%s", "pointlight", "float intensity", %f, "color lightcolor", (%f, %f, %f))\n' %
         (name, lamp.getEnergy() * self.LIGHTFACTOR, lamp.R, lamp.G, lamp.B))

   def distantlight(self, lamp, name):
      self.file.write('Light ("%s", "distantlight", "float intensity", %f, "color lightcolor", (%f, %f, %f))\n' %
         (name, lamp.getEnergy() * self.LIGHTFACTOR , lamp.R, lamp.G, lamp.B))

   def spotlight(self, lamp, name):
      self.file.write('Light ("%s", "spotlight", "float intensity", %f, "color lightcolor", (%f, %f, %f), "float coneangle", %f)\n' %
         (name, lamp.getEnergy() * self.LIGHTFACTOR , lamp.R, lamp.G, lamp.B, lamp.spotSize * pi/180.0))

   def light(self, obj):
      name = obj.name
      lamp = Blender.Lamp.Get(obj.getData().name)

      self.file.write('\nPushTransform ()\n')
      self.translate(obj)

      type = lamp.getType()
      if (type == Blender.Lamp.Types['Lamp']):
         self.pointlight(lamp, name)
      elif (type == Blender.Lamp.Types['Spot']):
         self.spotlight(lamp, name)
      elif (type == Blender.Lamp.Types['Sun']):
         self.distantlight(lamp, name)

      self.file.write('PopTransform ()\n')

   def lights(self):
      self.ambientlight()
      for obj in self.objects:
         type = obj.getType()
         if (type == 'Lamp'):
            self.light(obj)

   def geometries(self):
      for obj in self.objects:
         type = obj.getType()
         if (type == 'Mesh'):
            self.mesh(obj)

   def export(self, scene):
      self.scene   = scene
      self.objects = scene.getChildren()
      if (self.verbose > 1) : print 'Info: starting Gelato pyg export to', self.filename
      self.head()
      self.lights()
      self.geometries()
      self.tail()
      if (self.verbose > 1) : print 'Info: finished Gelato pyg export'

scene = Blender.Scene.GetCurrent()

pyg = gelato_pyg(FILENAME, VERBOSE)
pyg.export(scene)

