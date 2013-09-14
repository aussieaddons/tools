#!/usr/bin/env python

import os
import zipfile
import shutil
import glob
import xml.dom.minidom as DOM

EXCLUDE_EXTS = ['.pyc', '.pyo', '.swp', '.zip', '.gitignore']
EXCLUDE_DIRS = ['.git']
EXCLUDE_FILES = []

dom = DOM.parse('addon.xml')
addon_info = dom.getElementsByTagName('addon').item(0)
name = addon_info.getAttribute('id')
version = addon_info.getAttribute('version')

zfilename = "%s-%s.zip" % (name, version)
print("Writing ZIP file: %s" % zfilename)
# Walk the directory to create the zip file
z = zipfile.ZipFile(zfilename, 'w')
for r, d, f in os.walk('.'):
  for ff in f:
    skip = False

    # If it's not one of the files we're excluding
    for ext in EXCLUDE_EXTS:
      if ff.endswith(ext):
        skip = True

    # Skip any files
    for fn in EXCLUDE_FILES:
      if ff == fn:
        skip = True

    # Skip any directories
    for dr in EXCLUDE_DIRS:
      if (r.find(dr) > -1) or (r.find('deps') > -1):
        skip = True

    if not skip: 
      z.write(os.path.join(r, ff), os.path.join(name, r, ff), zipfile.ZIP_DEFLATED)
z.close()

# Build XBMC ZIP file with all required depenencies if deps
# directory exists
if os.path.isdir(os.path.join('resources','lib','deps')):
  zfilename = "%s-%s_deps.zip" % (name, version)

  # Walk the directory to create the zip file
  print("Writing ZIP file: %s" % zfilename)
  z = zipfile.ZipFile(zfilename, 'w')
  for r, d, f in os.walk('.'):
    for ff in f:
      skip = False

      # If it's not one of the files we're excluding
      for ext in EXCLUDE_EXTS:
        if ff.endswith(ext):
          skip = True

      # Skip any files
      for fn in EXCLUDE_FILES:
        if ff == fn:
          skip = True

      # Skip any directories
      for dr in EXCLUDE_DIRS:
        if r.find(dr) > -1:
          skip = True

      if not skip:
        z.write(os.path.join(r, ff), os.path.join(name, r, ff), zipfile.ZIP_DEFLATED)
  z.close()
