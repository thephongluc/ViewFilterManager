"""Version derives from the build-generated content VERSION or source root."""
import io
import os
content = os.path.dirname(os.path.dirname(__file__))
path = os.path.join(content, 'VERSION')
if not os.path.isfile(path):
    path = os.path.join(os.path.dirname(content), 'VERSION')
with io.open(path, 'r', encoding='utf-8') as stream:
    __version__ = stream.read().strip()
