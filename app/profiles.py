import json
import re
from pathlib import Path
from threading import Timer
from typing import Sequence, List

from pydantic import parse_obj_as, RootModel
from pyld import jsonld
from rdflib import Graph

from app.model import Model


RELOAD_TIME = 60 * 5

LOAD_PROFILES_SPARQL = '''
PREFIX chekp: <urn:chek:profiles/>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX prof: <http://www.w3.org/ns/dx/prof/>
PREFIX sd: <https://w3id.org/okn/o/sd#>
PREFIX role: <http://www.w3.org/ns/dx/prof/role/>
CONSTRUCT {
} WHERE {
  SERVICE <__SERVICE__> {
    ?uri a chekp:Profile .
    OPTIONAL { ?uri dct:title ?title }
    OPTIONAL { ?uri prof:hasToken ?token }
    OPTIONAL { ?uri prof:isProfileOf ?profileOf }
    OPTIONAL { 
      ?uri prof:hasResource ?resource .
      ?resource prof:hasRole role:validation ;
        dct:format ?format ;
        dct:conformsTo <https://www.w3.org/TR/shacl/> ;
        prof:hasArtifact ?artifact .
    }
    OPTIONAL { 
      ?uri sd:hasParameter ?param .
      ?param dct:identifier ?identifier ;
          sd:hasDataType ?dataType .
      OPTIONAL { ?param dct:description ?description }
    }
  }
}
'''

LOAD_PROFILES_FRAME = json.loads('''
{
  "@context": {
    "checkp": "urn:chek:profiles/",
    "prof": "http://www.w3.org/ns/dx/prof/",
    "sd": "https://w3id.org/okn/o/sd#",
    "dct": "http://purl.org/dc/terms/",
    "uri": "@id",
    "title": "dct:title",
    "description": "dct:description",
    "identifier": "dct:identifier",
    "dataType": "sd:hasDataType",
    "parameters": {
      "@id": "sd:hasParameter",
      "@container": "@set"
    },
    "resources": {
      "@id": "prof:hasResource",
      "@container": "@set"
    },
    "conformsTo": {
      "@id": "dct:conformsTo",
      "@type": "@id"
    },
    "token": "prof:hasToken",
    "profileOf": {
      "@id": "prof:isProfileOf",
      "@type": "@id",
      "@container": "@set"
    },
    "artifacts": {
      "@id": "prof:hasArtifact",
      "@type": "@id",
      "@container": "@set"
    },
    "format": {
      "@id": "dct:format",
      "@type": "@id"
    },
    "role": {
      "@id": "prof:hasRole",
      "@type": "@id"
    }
  },
  "@type": "checkp:Profile",
  "resources": {},
  "parameters": {}
}
''')


class Resource(Model):
    role: str
    format: str | None
    conformsTo: str | None
    artifacts: list[str] = []


class Parameter(Model):
    identifier: str
    description: str | None
    dataType: str


class Profile(Model):
    uri: str
    title: str | None
    token: str | None
    profileOf: list[str] = []
    resources: list[Resource] = []
    parameters: list[Parameter] = []


ProfileList = RootModel[List[Profile]]


class ProfileLoader:

    def __init__(self, source: str):
        self.profiles: dict[str, Profile] = {}

        self._is_sparql = source.startswith('sparql:')
        self.source = source[len('sparql:') if self._is_sparql else 0:]

        self._reload_timer = None

        self._reload_profiles()

    def _reload_profiles(self):
        g = Graph()
        if self._is_sparql:
            g = g.query(LOAD_PROFILES_SPARQL.replace('__SERVICE__', self.source)).graph
        else:
            if re.match(r'^https?://', self.source):
                g.parse(self.source)
            else:
                files = set()
                for p in Path().glob(self.source):
                    if p.is_file():
                        files.add(p)
                    else:
                        files.update(p.glob('**/*'))

                if not files:
                    raise ValueError(f'No files found for source {self.source}')
                for file in files:
                    g.parse(file)

        profiles_obj = jsonld.frame(json.loads(g.serialize(format='json-ld')),
                                LOAD_PROFILES_FRAME)
        if '@graph' in profiles_obj:
            profiles_obj = profiles_obj['@graph']
        else:
            profiles_obj = [profiles_obj]

        profiles = parse_obj_as(List[Profile], profiles_obj)
        self.profiles = {profile.uri: profile for profile in sorted(profiles, key=lambda p: (p.token, p.uri))}

        self._schedule_reload()

    def _schedule_reload(self):
        if not self._is_sparql:
            return
        timer = Timer(RELOAD_TIME, self._reload_profiles)
        timer.daemon = True
        self._reload_timer = timer
        timer.start()

    @property
    def is_local_source(self):
        return not self._is_sparql

    @property
    def is_sparql_source(self):
        return self._is_sparql

    def close(self):
        if self._reload_timer:
            self._reload_timer.cancel()
