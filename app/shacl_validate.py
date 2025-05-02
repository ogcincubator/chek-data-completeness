import sys

from pyparsing import ParseException
from rdflib import Graph
from pyshacl import validate

def _main(source, shacl_source, output):

    g = Graph().parse(source)
    shacl_graph = Graph().parse(shacl_source)

    try:
        conforms, report_graph, report_text = validate(g, shacl_graph=shacl_graph, advanced=True, inplace=True)
        report_graph.serialize(output, format="json-ld")
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    _main(*sys.argv[1:4])
