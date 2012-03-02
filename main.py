import cgi
import os
import hmac
import simplejson as json
import re
import logging
import base64
import zipimport
import urllib
import htmlentitydefs

from datetime import datetime;
from urlparse import urlparse;

from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.ext import search
from google.appengine.ext.webapp import template

IMAGE_BUNDLE_SIZE = 2500
MEMCACHE_DATA_TIMEOUT = 24 * 60 * 60
MEMCACHE_PAGE_TIMEOUT = 24 * 60 * 60

image_zips = {}

class UnicodeData():     
    cached_unicode_data = {}
    cached_unicode_classes = None
    cached_cjk_definitions = None
    cached_unicode_blocks = None
    
    cached_unicode_zip = None
    cached_unihan_zip = None

    def name_to_slug(self, name):
        return re.sub("(^-+)|(-+$)", "", re.sub("[^A-Za-z]+", "-", name)).lower();

    def get_unicode_zip(self):
        if not self.cached_unicode_zip:
            self.cached_unicode_zip = zipimport.zipimporter("UCD-5.2.0.zip")
            
        return self.cached_unicode_zip

    def get_unihan_zip(self):
        if not self.cached_unihan_zip:
            self.cached_unihan_zip = zipimport.zipimporter("Unihan-5.2.0.zip")
            
        return self.cached_unihan_zip

    def get_unicode_data(self, id):
        RANGE_SIZE = 35000
        range = id // RANGE_SIZE
        
        if self.cached_unicode_data.has_key(range):
            return self.cached_unicode_data[range]
        
        self.cached_unicode_data[range] = memcache.get("cached_unicode_data.%s" % range)
        if self.cached_unicode_data[range]:
            return self.cached_unicode_data[range]
        
        unicode_data = {}
        for line in self.get_unicode_zip().get_data("UnicodeData.txt").split('\n'):
            if len(line) > 0:
                id = int(line[:line.find(';')], 16)
                if not unicode_data.has_key(id // RANGE_SIZE):
                    unicode_data[id // RANGE_SIZE] = {}
                unicode_data[id // RANGE_SIZE][id] = line

        for key in unicode_data:
            memcache.add("cached_unicode_data.%s" % key, unicode_data[key], MEMCACHE_DATA_TIMEOUT)
        self.cached_unicode_data = unicode_data
        return self.cached_unicode_data[range]

    def get_unicode_classes(self):
        if not self.cached_unicode_classes:
            self.cached_unicode_classes = memcache.get("cached_unicode_classes")
            if self.cached_unicode_classes:
                return self.cached_unicode_classes
            unicode_classes = {}
            for line in self.get_unicode_zip().get_data("PropertyValueAliases.txt").split('\n'):
                if line[:4] == "gc ;":
                    unicode_classes[line[5:7].strip()] = line[17:45].strip().replace("_", " ")
            self.cached_unicode_classes = unicode_classes
            memcache.add("cached_unicode_classes", self.cached_unicode_classes, MEMCACHE_DATA_TIMEOUT)
            
        return self.cached_unicode_classes 

    def get_unicode_blocks(self):
        if not self.cached_unicode_blocks:
            self.cached_unicode_blocks = memcache.get("cached_unicode_blocks")
            if self.cached_unicode_blocks:
                return self.cached_unicode_blocks
            unicode_blocks = []
            for line in self.get_unicode_zip().get_data("Blocks.txt").split('\n'):
                if len(line) > 0 and line[0] != "#" and line[0] != " ":
                    semi_split = line.split("; ")
                    name = semi_split[1]
                    range = semi_split[0].split(r"..")
                    unicode_blocks.append([int(range[0], 16), int(range[1], 16), name])
                    
            self.cached_unicode_blocks = unicode_blocks
            memcache.add("cached_unicode_blocks", self.cached_unicode_blocks, MEMCACHE_DATA_TIMEOUT)
            
        return self.cached_unicode_blocks
    
    def get_cjk_definitions(self):
        if not self.cached_cjk_definitions:            
            self.cached_cjk_definitions = memcache.get("cached_cjk_definitions")
            if self.cached_cjk_definitions:
                return self.cached_cjk_definitions
            cjk_definitions = {}
            for line in self.get_unihan_zip().get_data("Unihan_Readings.txt").split('\n'):
                bits = re.split(r"\s+", line, 2)
                if len(bits) > 2 and bits[1] == "kDefinition":
                    cjk_definitions[int(bits[0][2:], 16)] = bits[2]
            self.cached_cjk_definitions = cjk_definitions
            memcache.add("cached_cjk_definitions", self.cached_cjk_definitions, MEMCACHE_DATA_TIMEOUT)
                    
        return self.cached_cjk_definitions

    def unichr(self, id):
        return eval('u"\U%08x"' % id)

    def process_decomposition(self, data):
        if data.find('>') > -1:
            data = data[data.find('>') + 1:]
        data = "".join([self.unichr(int(x, 16)) for x in data.split(" ") if x])
        return data

    def dump_chars(self, data):
        return [self.get_data(ord(x), False) for x in data]

    def get_data(self, id, recursive):
        if id < 0 or id > 0x10ffff:
            return None
        
        unicode_data = self.get_unicode_data(id)
        unicode_classes = self.get_unicode_classes()
        cjk_definition = ""
        
        if id != 0x4e00 and unicode_data.has_key(id):
            data = unicode_data[id].split(';')
        else:
            cjk_definitions = self.get_cjk_definitions()
            if cjk_definitions.has_key(id):
                data = [hex(id)[2:].upper(), "CJK UNIFIED IDEOGRAPH", "Cn", "", "", "", "", "", ""]
                cjk_definition = cjk_definitions[id]
            else:
                data = [hex(id)[2:].upper(), "INVALID CHARACTER", "Cn", "", "", "", "", "", ""]
            
        name = data[10] if data[2] == "Cc" else data[1]
        
        unicode_blocks = self.get_unicode_blocks()
        block = None
        for line in unicode_blocks:
            if id >= line[0] and id <= line[1]:
                block = line[2]
                break
        
        unicodeString = self.unichr(id) 
        longEscape = '"' + "".join(["\\u%02x%02x" % (ord(y[0]), ord(y[1])) for y in zip(unicodeString.encode('utf-16be')[0::2], unicodeString.encode('utf-16be')[1::2])]) + '"' 
        shortEscape = longEscape if id > 255 else '"\\x%s"' % data[0][2:].lower()
        decomposition = self.process_decomposition(data[5]) if data[5] else ""
        decompositionChars = self.dump_chars(decomposition) if recursive else []
        
        return { 
            'id': id,
            'char': None if data[2] == 'Cc' else unicodeString,
            'hexId': 'U+' + data[0],
            'name': name,
            'link': '/%s-unicode-%s' % (data[0].lower(), self.name_to_slug(name)),
            'class': "%s (%s)" % (unicode_classes[data[2]], data[2]),
            'block': block,
            'blockLink': '/block/%s' % self.name_to_slug(block),
            'numericValue': data[8],
            'cjkDefinition': cjk_definition,
            'decomposition': decomposition,
            'decompositionChars' : decompositionChars,
            'javaEscape': longEscape,
            'javascriptEscape': shortEscape,
            'pythonEscape': repr(unicodeString),
            'htmlEscape': "&%s;" % htmlentitydefs.codepoint2name[id] if htmlentitydefs.codepoint2name.has_key(id) else "&#%s; &#x%04x; " % (id, id),
            'xmlEscape': "&#%s; &#x%04x; " % (id, id),
            'urlEncoded': urllib.urlencode({'q': unicodeString.encode('utf-8')}),
            'utf8': " ".join(["%02x" % ord(x) for x in unicodeString.encode('utf-8')]),
            'utf16': " ".join(["%02x%02x" % (ord(y[0]), ord(y[1])) for y in zip(unicodeString.encode('utf-16be')[0::2], unicodeString.encode('utf-16be')[1::2])]),
        }
    

unicode_data = UnicodeData()


class MainPage(webapp.RequestHandler):
    def get(self):       
        top_chars = [unicode_data.get_data(x, False) for x in 
                      [0x2603, 0x2602, 0x2620, 0x2622, 0x3020, 0x2368, 0xFDFA,
                       0x0E5B, 0x2619, 0x2764, 0x203D, 0x0F12, 0x0F17]]
        template_values = { 'top_chars': top_chars }
        
        path = os.path.join(os.path.dirname(__file__), 'templates/index.html')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8';
        rendered_front_page = template.render(path, template_values)
        self.response.out.write(rendered_front_page)


class HtmlEntitiesPage(webapp.RequestHandler):
    def get(self):       
        keys = htmlentitydefs.codepoint2name.keys()
        keys.sort()
        entities = [unicode_data.get_data(x, False) for x in keys]
        template_values = { 'entities': entities }
        
        path = os.path.join(os.path.dirname(__file__), 'templates/htmlentities.html')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8';
        rendered_front_page = template.render(path, template_values)
        self.response.out.write(rendered_front_page)


class BlockPage(webapp.RequestHandler):
    def get(self, slug):     
        found = None  
        for block in unicode_data.get_unicode_blocks():
            slug_check = unicode_data.name_to_slug(block[2])
            if slug_check == slug:
                found = block
                break
        
        if not found:
            return
        
        entities = [unicode_data.get_data(x, False) for x in range(block[0], block[1] + 1)]
        entities = [x for x in entities if x['name'] != "INVALID CHARACTER"]
        template_values = { 'entities': entities, 'block': block[2] }
        
        path = os.path.join(os.path.dirname(__file__), 'templates/block.html')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8';
        rendered_front_page = template.render(path, template_values)
        self.response.out.write(rendered_front_page)

class GlyphPage(webapp.RequestHandler):
    def get(self, id, desc):
        try:
            id = int(id, 16)
        except ValueError:
            self.redirect('/')
            return
        
        template_values = {
                           'previous':unicode_data.get_data(id - 1, False),
                           'next': unicode_data.get_data(id + 1, False),
                           'glyph': unicode_data.get_data(id, True),
                           }

        path = os.path.join(os.path.dirname(__file__), 'templates/glyph.html')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8';
        rendered_front_page = template.render(path, template_values)
        self.response.out.write(rendered_front_page)


class SavePage(webapp.RequestHandler):
    def post(self):
        data = self.request.body
        data = data[data.find(',') + 1:]
        data = base64.b64decode(data)

        f = open.__base__("static/images/" + self.request.query_string + ".png", "wb")
        f.write(data)
        self.response.out.write("OK")

class GlyphImage(webapp.RequestHandler):
    def get(self, glyphNumber):
        
        segment = (int(glyphNumber) // IMAGE_BUNDLE_SIZE) * IMAGE_BUNDLE_SIZE
        self.response.headers['Content-Type'] = 'image/png'
        
        if not image_zips.has_key(segment):
            file = "images/%s.zip" % segment
            if os.path.exists(file):
                image_zips[segment] = zipimport.zipimporter(file)
            else:
                image_zips[segment] = None
                
        if image_zips[segment]:
            try:
                self.response.out.write(image_zips[segment].get_data("%s.png" % (glyphNumber)))
                return
            except IOError:
                pass

        self.response.out.write(open("images/no-glyph.png", "rb").read())

class Error404(webapp.RequestHandler):
    def get(self):
        self.redirect('/')
        return

application = webapp.WSGIApplication(
                                     [
                                      ('/', MainPage),
                                      ('/html-entities', HtmlEntitiesPage),
                                      ('/block/(.*)', BlockPage),
                                      ('/save', SavePage),
                                      (r'/images/glyph/([0-9]+)', GlyphImage),
                                      (r'/([a-z0-9A-Z]+)(-.*)?', GlyphPage),
                                      ('/.*', Error404)
                                     ],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

