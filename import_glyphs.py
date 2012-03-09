import glob
from google.appengine.api import datastore

files = glob.glob("static/images/*.png")

groupsize = 50
groups = [[x for x in files[i:i+groupsize]] for i in range(0,len(files),groupsize)]
count = 0
for group in groups:
	count += len(group)
	print count
	entities = []
	for glyph in group:
		e = datastore.Entity(kind='glyph', name=glyph.split('/')[2].split('.')[0])
		e['data'] = db.Blob(open(glyph).read())
		entities.append(e)
	datastore.Put(entities)
