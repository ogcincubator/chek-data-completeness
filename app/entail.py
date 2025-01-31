import sys

from rdflib import Graph
from pyshacl import validate

def entail(source, shacl_source, output):
    g = Graph().parse(source)
    shacl_graph = Graph().parse(shacl_source)

    validate(g, shacl_graph=shacl_graph, advanced=True, inplace=True)
    g.serialize(output, format="turtle")


if __name__ == '__main__':
    entail(*sys.argv[1:4])
