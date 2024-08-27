import json
import os.path
import re
from pathlib import Path
from threading import Timer
from typing import Sequence, List
from urllib.parse import unquote, urlparse

from pydantic import parse_obj_as, RootModel, field_serializer, TypeAdapter
from pyld import jsonld
from rdflib import Graph

from app import model
from app.model import Model

RELOAD_TIME = 60 * 5

COMMON_INPUTS = {
    'cityFiles': model.InputDescription(
        title='Input data file',
        description='Input data file (CityJSON or CityGML)',
        minOccurs=1,
        maxOccurs=model.MaxOccurs.unbounded,
        schema=model.Schema(
            type='object',
            properties={
                'name': model.Schema(
                    type='string',
                    description='Name or alias for this file',
                ),
                'data_str': model.Schema(
                    type='string',
                    description='Data string for this file (CityJSON or CityGML)',
                )
            },
            required={
                'data_str',
            }
        ),
    ),
}

LOAD_PROFILES_SPARQL = '''
PREFIX chekp: <urn:chek:profiles/>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX prof: <http://www.w3.org/ns/dx/prof/>
PREFIX sd: <https://w3id.org/okn/o/sd#>
PREFIX role: <http://www.w3.org/ns/dx/prof/role/>
PREFIX hydra: <http://www.w3.org/ns/hydra/core#>
CONSTRUCT {
} WHERE {
  SERVICE <__SERVICE__> {
    ?uri a chekp:Profile .
    OPTIONAL { ?uri dct:hasVersion ?version }
    OPTIONAL { ?uri dct:title ?title }
    OPTIONAL { ?uri dct:description ?description }
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
      OPTIONAL { ?param hydra:required ?required }
    }
  }
}
'''

LOAD_PROFILES_FRAME = json.loads('''
{
  "@context": {
    "prof": "http://www.w3.org/ns/dx/prof/",
    "sd": "https://w3id.org/okn/o/sd#",
    "dct": "http://purl.org/dc/terms/",
    "hydra": "http://www.w3.org/ns/hydra/core#",
    "uri": "@id",
    "title": "dct:title",
    "description": "dct:description",
    "identifier": "dct:identifier",
    "dataType": "sd:hasDataType",
    "version": "dct:version",
    "required": "hydra:required",
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
  "@type": "urn:chek:profiles/Profile",
  "resources": {},
  "parameters": {},
  "@embed": "@never"
}
''')


class Resource(Model):
    role: str
    format: str | None = None
    conformsTo: str | None = ''
    artifacts: list[str] = []

    @field_serializer('artifacts')
    def serialize_artifacts(self, artifacts: list[str], _info):
        return [a if re.match('^https?://', a)
                else os.path.relpath(unquote(urlparse(a).path))
                for a in artifacts]


class Parameter(Model):
    identifier: str
    description: str | None
    dataType: str
    required: bool = False


class Profile(Model):
    uri: str
    title: str | None = None
    description: str | None = None
    token: str | None = None
    version: str = ''
    profileOf: list[str] = []
    resources: list[Resource] = []
    parameters: list[Parameter] = []

    def get_id(self):
        if self.token:
            return self.token
        # Remove URL scheme
        uri_id = re.sub(r'^https?://', '', str(self.uri))
        # Keep only allowed characters
        uri_id = re.sub(r'[^A-Za-z0-9_-]+', '_', uri_id)
        return uri_id

    def to_process_summary(self) -> model.ProcessSummary:
        return model.ProcessSummary(
            id=self.get_id(),
            version=self.version,
            title=self.title,
            description=self.description,
        )

    def to_process_description(self) -> model.Process:
        inputs: dict[str, model.InputDescription] = {
            **COMMON_INPUTS,
            **{
                param.identifier: model.InputDescription(
                    title=param.identifier,
                    description=param.description,
                    minOccurs=1 if param.required else 0,
                    maxOccurs=1,
                    schema=model.Schema(
                        type=param.dataType,
                    ),
                ) for param in self.parameters
            },
        }
        return model.Process(
            **self.to_process_summary().model_dump(by_alias=True),
            inputs=inputs,
            # TODO: outputs
        )


ProfileList = RootModel[List[Profile]]


class ProfileLoader:

    def __init__(self, source: str):
        self.profiles: dict[str, Profile] = {}
        self.profiles_by_uri: dict[str, Profile] = {}
        self.profile_shacl: dict[str, Graph] = {}

        self._is_sparql = source.startswith('sparql:')
        self.source = source[len('sparql:') if self._is_sparql else 0:]

        self._reload_timer = None

        self._reload_profiles()

    def _reload_profiles(self):
        self.profiles = {}
        self.profile_shacl = {}
        g = Graph()
        if self._is_sparql:
            g = g.query(LOAD_PROFILES_SPARQL.replace('__SERVICE__', self.source)).graph
        else:
            if re.match(r'^https?://', self.source):
                g.parse(self.source)
            else:
                files = set()
                for path in Path().glob(self.source):
                    if path.is_file():
                        files.add(path)
                    else:
                        files.update(path.glob('**/*'))
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

        profiles = TypeAdapter(List[Profile]).validate_python(profiles_obj)

        self.profiles = {profile.get_id(): profile
                         for profile in sorted(profiles, key=lambda x: (x.token, x.uri))}
        self.profiles_by_uri = {profile.uri: profile for profile in profiles}

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
