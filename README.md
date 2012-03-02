This is the AppEngine source for Charbase. I'm not a native Python developer, so there may be bits of code in here that are decidedly un-Pythonic. Pull requests to remedy this 
are welcome.

As this was written pre-Blobstore, the images for the characters are rendered using a browser canvas, saved on a development machine, then zipped and included in the bundle of 
static files that are pushed to the server. This should be rewritten to store the glyph images in the blobstore. There's a lot of work that could be done on character generation 
as well - some of the glyphs are clipped by the box.

The current code doesn't support anything outside of the Basic Multilingual Plane.

Todo list:

 * Migrate to the AppEngine blobstore for storing data
 * Show combining characters alongside an actual 
 * Make search work
