"""Export the code-native icon.svg geometry to transparent PNG and Windows ICO.

Run with Pillow installed. The generous canvas and rounded strokes remain
legible at Revit's 16/32 px ribbon sizes. No reference image is embedded.
"""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'runtime'
scale = 16
image = Image.new('RGBA', (64 * scale, 64 * scale))
draw = ImageDraw.Draw(image)
ink = '#111111'

def stroke(points, width):
    vertices = [(x * scale, y * scale) for x, y in points]
    draw.line(vertices, fill=ink, width=round(width * scale), joint='curve')
    radius = width * scale / 2
    for x, y in vertices:
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=ink)

stroke([(8,9), (44,9), (44,18), (28,34), (28,43), (20,49), (20,34), (8,18), (8,9)], 5.5)
draw.ellipse(tuple(round(v * scale) for v in (28.75, 26.75, 57.25, 55.25)), fill=ink)
draw.ellipse(tuple(round(v * scale) for v in (34.25, 32.25, 51.75, 49.75)), fill=(0,0,0,0))
stroke([(51.5,49.5), (59,57)], 7)
for size, filename in [(16,'icon16.png'), (32,'icon32.png'), (64,'icon.png'), (256,'icon256.png')]:
    image.resize((size,size), Image.Resampling.LANCZOS).save(root / filename)
image.resize((256,256), Image.Resampling.LANCZOS).save(root / 'icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
