import json
import os.path
import re
from collections import deque
from pathlib import Path
from threading import Timer
from typing import List
from urllib.parse import unquote, urlparse

import requests
from pydantic import RootModel, field_serializer, TypeAdapter
from pyld import jsonld
from rdflib import Graph

from app import model
from app.model import Model

RELOAD_TIME = 60 * 20

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
    "prof-role": "http://www.w3.org/ns/dx/prof/role/",
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
    "validation": "http://www.w3.org/ns/dx/prof/role/validation",
    "SHACL": "https://www.w3.org/TR/shacl/",
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
    profileOf: set[str] = set()
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
            links=([model.Link(title='Profile of', rel='profileOf', href=p) for p in self.profileOf]
                   + [model.Link(title='Profile URI', rel='canonical', href=self.uri)]),
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


def _load_bblocks_profiles(source: str) -> list[Profile]:
    seen_registers = set()
    pending_registers = deque()
    pending_registers.append(source)
    bblocks_dependencies = {}
    profiles = {}
    while pending_registers:
        register_url = pending_registers.popleft()
        if register_url in seen_registers:
            continue
        r = requests.get(register_url)
        r.raise_for_status()
        register = r.json()
        for bblock in register['bblocks']:
            bblock_id = bblock['itemIdentifier']
            if not bblock.get('rdfData') or 'chek-validation-profile' not in bblock.get('tags', []):
                continue
            g = Graph()
            for d in bblock['rdfData']:
                g.parse(d)
            profile_obj = jsonld.frame(json.loads(g.serialize(format='json-ld')),
                                       LOAD_PROFILES_FRAME)
            profile_obj.setdefault('profileOf', []).append('urn:chek:profiles/chek')
            profile_obj['resources'] = [{
                'role': 'prof-role:validation',
                'conformsTo': 'https://www.w3.org/TR/shacl/',
                'format': 'https://w3id.org/mediatype/text/turtle',
                'artifacts': [s for s in bblock.get('shaclRules', {}).get(bblock_id, [])],
            }]
            profiles[bblock['itemIdentifier']] = Profile.model_validate(profile_obj)

            if bblock.get('dependsOn'):
                bblocks_dependencies[bblock['itemIdentifier']] = bblock['dependsOn']

        for imported_reg in register.get('imports', []):
            if imported_reg not in seen_registers:
                pending_registers.append(imported_reg)

        seen_registers.add(register_url)

    # Resolve dependencies
    for bblock_id, bblock_dep_ids in bblocks_dependencies.items():
        profile = profiles[bblock_id]
        for bblock_dep_id in bblock_dep_ids:
            bblock_dep = profiles.get(bblock_dep_id)
            if not bblock_dep:
                raise ValueError(f"Unmet Building Block dependency {bblock_id} -> {bblock_dep}")
            profile.profileOf.add(bblock_dep.uri)

    return list(profiles.values())


def _load_profiles_from_source(source: str) -> tuple[list[Profile], bool]:
    needs_reload = False
    g = Graph()
    if source.startswith('sparql:'):
        g = g.query(LOAD_PROFILES_SPARQL.replace('__SERVICE__', source[len('sparql:'):])).graph
        needs_reload = True
    elif source.startswith('bblocks:'):
        return _load_bblocks_profiles(source[len('bblocks:'):]), True
    else:
        if re.match(r'^https?://', source):
            g.parse(source)
            needs_reload = True
        else:
            files = set()
            for path in Path().glob(source):
                if path.is_file():
                    files.add(path)
                else:
                    files.update(path.glob('**/*'))
            if not files:
                raise ValueError(f'No files found for source {source}')
            for file in files:
                g.parse(file)

    profiles_obj = jsonld.frame(json.loads(g.serialize(format='json-ld')),
                                LOAD_PROFILES_FRAME)
    if '@graph' in profiles_obj:
        profiles_obj = profiles_obj['@graph']
    else:
        profiles_obj = [profiles_obj]

    profiles = TypeAdapter(List[Profile]).validate_python(profiles_obj)

    return profiles, needs_reload


class ProfileLoader:

    def __init__(self, source: str | list[str]):
        self.source = [source] if isinstance(source, str) else source
        self.profiles: dict[str, Profile] = {}
        self.profiles_by_uri: dict[str, Profile] = {}
        self.profile_shacl: dict[str, Graph] = {}

        self._needs_reload = False
        self._reload_timer = None

        self._reload_profiles()

    def _reload_profiles(self):
        self.profiles = {}
        self.profile_shacl = {}
        self._needs_reload = False
        for source in self.source:
            source_profiles, needs_reload = _load_profiles_from_source(source)
            self._needs_reload = self._needs_reload or needs_reload
            self.profiles.update({profile.get_id(): profile
                                  for profile in sorted(source_profiles, key=lambda x: (x.token, x.uri))})

        self.profiles_by_uri = {profile.uri: profile for profile in self.profiles.values()}

        self._schedule_reload()

    def _schedule_reload(self):
        if not self._needs_reload:
            return
        timer = Timer(RELOAD_TIME, self._reload_profiles)
        timer.daemon = True
        self._reload_timer = timer
        timer.start()

    def close(self):
        if self._reload_timer:
            self._reload_timer.cancel()
