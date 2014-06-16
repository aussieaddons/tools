#!/usr/bin/env python

import argparse
import codecs
import hashlib
import json
import re
import os
import os.path
import sys
from urllib2 import urlopen
import xml.dom.minidom as DOM

repo_index = None

def fatal_error(error_msg, status_code=1):
    sys.stderr.write("Error: %s\n" % error_msg)
    sys.exit(status_code)

def is_version_number(string):
    try:
        version_number(string)
        return True
    except argparse.ArgumentTypeError:
        return False

def version_number(string):
    match = re.match(r'(\d+).(\d+)(?:\.(\d+))?', string, re.VERBOSE)
    if not match:
        msg = "%r is not a valid version number" % string
        raise argparse.ArgumentTypeError(msg)

    numbers = [n for n in match.groups() if n]
    ver = '.'.join(tuple(numbers))
    return ver

def read_repo_index():
    global repo_index
    if repo_index is None:
        repo_index = DOM.parse('addons.xml')
    return repo_index

def save_repo_index():
    if repo_index is not None:
        f = codecs.open('addons.xml', 'w', 'utf-8')
        repo_index.writexml(f)
        f.close()
        git_add_file('addons.xml')

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

def update_repo_md5():
    md5 = calculate_md5('addons.xml')
    f = open('addons.xml.md5', 'w')
    f.write(md5)
    f.close()
    git_add_file('addons.xml.md5')

def find_addon(addon_id):
    dom = read_repo_index()
    addons = dom.getElementsByTagName('addon')
    for addon in addons:
        if addon.getAttribute('id') == addon_id:
            return addon

def fetch_tags(repo_name):
    url = 'https://api.github.com/repos/xbmc-catchuptv-au/%s/tags' % repo_name
    return json.load(urlopen(url))

def filter_tags(repo_name):
    tags = fetch_tags(repo_name)
    return filter(lambda tag: is_version_number(tag['name'][1::]), tags)

def find_tag(repo_name, tag_name):
    tags = fetch_tags(repo_name)
    for tag in tags:
        if tag['name'] == tag_name:
            return tag

def find_latest_tag(repo_name):
    tags = filter_tags(repo_name)
    return sorted(tags, key=lambda tag: tag['name'].split('.'), reverse=True)[0]

def download_file(url, out):
    u = urlopen(url)
    if os.path.isfile(out):
        fatal_error("File already exists: %s" % out)
    f = open(out, 'wb')
    print "Downloading %s" % url

    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break
        f.write(buffer)

    f.close()

def download_addon(addon_id, tag):
    version = tag['name'][1::]
    download_file(tag['zipball_url'], "%s/%s-%s.zip" % (addon_id, addon_id, version))
    git_add_file("%s/%s-%s.zip" % (addon_id, addon_id, version))
    download_file("https://raw.githubusercontent.com/xbmc-catchuptv-au/%s/v%s/changelog.txt" % (addon_id, version), "%s/changelog-%s.zip" % (addon_id, version))
    git_add_file("%s/changelog-%s.zip" % (addon_id, version))

def get_output(cmd):
    pipe = os.popen(cmd, 'r')
    text = pipe.read().rstrip('\n')
    status = pipe.close() or 0
    return status, text

def git_add_file(f):
    n, result = get_output("git add \"%s\"" % f)
    if n:
        print('WARNING: git add failed with: %s %s' % (n, result))
        return False
    return True

def git_commit(message):
    n, result = get_output("git commit --no-verify -m '%s'" % message)
    if n:
        print('WARNING: git commit failed with: %s %s' % (n, result))
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update XBMC Addon Repo')
    parser.add_argument('ADDON_ID', help='Addon Unique Identifier, e.g. plugin.video.catchuptv.au.ten')
    parser.add_argument('-v', '--version', type=version_number, help='version number')
    parser.add_argument('-f', '--force', type=bool, help='Force update when version is lower than existing')
    args = parser.parse_args()

    addon = find_addon(args.ADDON_ID)
    if addon is None:
        fatal_error("Could not find \"%s\" in addons.xml" % args.ADDON_ID)

    if args.version is None:
        tag = find_latest_tag(args.ADDON_ID)

        if tag is None:
            fatal_error("No suitable tags found, ensure tag names are in the v0.1.2 format")
    else:
        tag = find_tag(args.ADDON_ID, 'v%s' % args.version)

        if tag is None:
            fatal_error("Could not find tagged version v%s" % args.version)

    existing_addon_version = addon.getAttribute('version')
    new_addon_version = tag['name'][1::]

    if not args.force and existing_addon_version.split('.') >= new_addon_version.split('.'):
        fatal_error("Addon in repo is the same version or higher (%s) than what is to be updated with (%s)" % (existing_addon_version, new_addon_version))

    print "Updating %s to %s" % (args.ADDON_ID, tag['name'])
    download_addon(args.ADDON_ID, tag)

    addon.setAttribute('version', new_addon_version)
    save_repo_index()
    update_repo_md5()
    git_commit("Update %s to %s" %  args.ADDON_ID, tag['name'])
