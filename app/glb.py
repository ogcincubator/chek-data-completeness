import base64
import sys

from cjio import cityjson


def convert(fn, outputfn):
    with open(fn) as f:
        cm = cityjson.reader(f)
    glb_data = cm.export2glb()
    glb_data.seek(0)
    with open(outputfn, 'wb') as f:
        base64.encode(glb_data, f)


if __name__ == '__main__':
    convert(*sys.argv[1:3])
