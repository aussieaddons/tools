#!/usr/bin/env python
import os
import os.path
import sys
import re
import hashlib
import xml.dom.minidom as DOM

from argparse import ArgumentParser
from codecs import open
from sh import git, cp
from zipfile import ZipFile, ZIP_DEFLATED

EXCLUDE_EXTS = ['.pyc', '.pyo', '.swp', '.zip', '.gitignore']
EXCLUDE_DIRS = ['.git']
EXCLUDE_FILES = []

CACHE_DIR = '.cache'

def version_is_gte(ver1, ver2):
  return tuple(map(lambda x: int(x), ver1.split('.'))) >= tuple(map(lambda x: int(x), ver2.split('.')))

def version_number(string):
  match = re.match(r'(\d+).(\d+)(?:\.(\d+))?', string, re.VERBOSE)
  if not match:
    msg = "%r is not a valid version number" % string
    raise argparse.ArgumentTypeError(msg)

  numbers = [n for n in match.groups() if n]
  ver = '.'.join(tuple(numbers))
  return ver

def calculate_md5(filename):
  md5 = hashlib.md5()
  block_sz = 8192
  f = open(filename, 'rb')
  while True:
    buffer = f.read(block_sz)
    if not buffer:
      break
    md5.update(buffer)
  return md5.hexdigest()

def fatal_error(error_msg, status_code=1):
  sys.stderr.write("Error: %s\n" % error_msg)
  sys.exit(status_code)

class DOMParser(object):
  def __init__(self, filename, dom=None, parent=None):
    self.filename = filename
    self.dom = dom or DOM.parse(self.filename)
    self.parent = parent

  def save(self):
    if self.parent:
      self.parent.save()
    else:
      f = open(self.filename, 'w', 'utf-8')
      self.dom.writexml(f)
      f.close()

class AddonIndexParser(DOMParser, dict):
  def __init__(self, filename='addons.xml', **kwargs):
    DOMParser.__init__(self, filename, **kwargs)
    dict.__init__(self)
    self.parse()

  def parse(self):
    for addon_dom in self.dom.getElementsByTagName('addon'):
      addon = AddonParser(dom=addon_dom, parent=self)
      self[addon['id']] = addon

  def update_md5(self):
    md5 = calculate_md5(self.filename)
    f = open('%s.md5' % self.filename, 'w')
    f.write(md5)
    f.close()

  def save(self):
    DOMParser.save(self)
    self.update_md5()

class AddonParser(DOMParser, dict):
  def __init__(self, filename='addon.xml', **kwargs):
    DOMParser.__init__(self, filename, **kwargs)
    dict.__init__(self)
    self.parse()

  def parse(self):
    self['id'] = self.dom.getAttribute('id')
    self['name'] = self.dom.getAttribute('name')
    self['version'] = self.dom.getAttribute('version')
    self['metadata'] = self.parse_metadata()

  def parse_metadata(self):
    metadata = dict()

    for extension in self.dom.getElementsByTagName('extension'):
      if extension.getAttribute('point') == 'xbmc.addon.metadata':
        for node in extension.childNodes:
          if node.nodeType == node.ELEMENT_NODE:
            rc = []
            for subnode in node.childNodes:
              if subnode.nodeType == subnode.TEXT_NODE:
                rc.append(subnode.data)
            metadata[node.tagName.lower()] = ''.join(rc)

    return metadata

  def update_version(self, version):
    self.dom.setAttribute('version', version)
    self.save()

class AddonCache():
  def __init__(self, addon):
    self.addon = addon
    self.source = addon['metadata']['source']
    self.dir = os.path.join(CACHE_DIR, addon['id'])
    self.git = git.bake(_cwd=self.dir)
    self.update()

  def is_dirty(self):
    dirty_state = self.git("diff", "--no-ext-diff", "--quiet", "--exit-code", _ok_code=[0,1]).exit_code == 1
    uncommited_changes = self.git("diff-index", "--cached", "--quiet", "HEAD", "--", _ok_code=[0,1]).exit_code == 1
    untracked_files = self.git("ls-files", "--others", "--exclude-standard", "--error-unmatch", "--", "'*'", _out=None, _err=None, _ok_code=[0,1]).exit_code != 1
    return dirty_state or uncommited_changes or untracked_files

  def checkout(self, tag):
    self.git.checkout(tag)

  def update(self):
    if not os.path.isdir(CACHE_DIR):
      os.makedirs(CACHE_DIR)

    if os.path.isdir(self.dir):
      if self.is_dirty():
        fatal_error("%s is dirty" % self.dir)
      self.git.checkout('master')
      self.git.pull()
    else:
      git.clone(addon['metadata']['source'], self.dir)

  def get_tags(self):
    return filter(lambda tag: re.match(r'^v(\d+).(\d+)(?:\.(\d+))?$', tag), self.git.tag().split("\n"))

  def get_latest_tag(self):
    return 'v%s' % '.'.join(map(lambda x: str(x), sorted(map(lambda tag: tuple(map(lambda x: int(x), tag[1::].split('.'))), self.get_tags()), reverse=True)[0]))

  def write_zip(self, filename):
    # from build_xbmc_zip.py

    z = ZipFile(filename, 'w')
    for r, d, f in os.walk(self.dir):
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
          z.write(os.path.join(r, ff), os.path.join(self.addon['id'], os.path.relpath(r, self.dir), ff), ZIP_DEFLATED)

    z.close()

if __name__ == '__main__':
  parser = ArgumentParser(description='Unoffical XBMC Addon Repo Updater Tool')
  parser.set_defaults(commit=True, force=False)
  parser.add_argument('addon_id', help='Addon Unique Identifier, e.g. plugin.video.catchuptv.au.ten')
  parser.add_argument('-v', '--version', type=version_number, help='Specify specific version to update to')
  parser.add_argument('-f', '--force', dest='force', action='store_true', help='Force update when version is older than the version currently in the repo')
  parser.add_argument('-nc', '--no-commit', dest='commit', action='store_false', help='Do not automatically commit changes')
  args = parser.parse_args()

  print("Reading addons.xml")
  addons = AddonIndexParser()
  if not addons.has_key(args.addon_id):
    fatal_error("%s not found in addons.xml" % args.addon_id)

  addon = addons[args.addon_id]
  if not addon['metadata'].has_key('source'):
    fatal_error("%s does not define a source in addons.xml" % addon['id'])

  print("Updating: %s" % addon['id'])
  cache = AddonCache(addon)

  version = args.version
  if version:
    tag = 'v%s' % version
  else:
    tag = cache.get_latest_tag()
    version = tag[1::]

  if not version_is_gte(version, addon['version']) and not args.force:
    fatal_error("Version specified (%s) is older than version in repo (%s)" % (version, addon['version']))

  print("Checking out: %s" % tag)
  cache.checkout(tag)

  print("Writing ZIP file: %s" % '%s-%s.zip' % (addon['id'], version))
  cache.write_zip(os.path.join(addon['id'], '%s-%s.zip' % (addon['id'], version)))
  git.add(os.path.join(addon['id'], '%s-%s.zip' % (addon['id'], version)))
  print("Writing icon file: %s" % 'icon.png')
  cp(os.path.join(cache.dir, 'icon.png'), os.path.join(addon['id'], 'icon.png'))
  git.add(os.path.join(addon['id'], 'icon.png'))
  print("Writing changelog: %s" % ('changelog-%s.txt' % version))
  cp(os.path.join(cache.dir, 'changelog.txt'), os.path.join(addon['id'], 'changelog-%s.txt' % version))
  git.add(os.path.join(addon['id'], 'changelog-%s.txt' % version))

  print("Updating addons.xml")
  addon.update_version(version)
  git.add('addons.xml')
  git.add('addons.xml.md5')

  if args.commit:
    git.commit(message="Update %s to %s" % (addon['name'], version))
