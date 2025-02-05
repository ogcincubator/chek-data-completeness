import json
import sys
from pathlib import Path

import jq
import jsonschema
import requests
from cachetools import TTLCache, cached
from rdflib import Graph
import yaml
import referencing


@cached(cache=TTLCache(maxsize=20, ttl=300))
def retrieve_yaml(uri: str):
    r = requests.get(uri)
    r.raise_for_status()
    return referencing.Resource.from_contents(yaml.safe_load(r.text))


schema_registry = referencing.Registry(retrieve=retrieve_yaml)


@cached(cache=TTLCache(maxsize=3, ttl=600))
def fetch_register(register_url: str) -> dict:
    r = requests.get(register_url)
    r.raise_for_status()
    return r.json()


@cached(cache=TTLCache(maxsize=20, ttl=300))
def fetch_bblock(register_url: str, bblock_id: str) -> tuple:
    register = fetch_register(register_url)
    bblock = next((b for b in register['bblocks'] if b['itemIdentifier'] == bblock_id), None)
    if not bblock:
        raise ValueError(f'Building Block {bblock_id} not found in {register_url}')

    schema_url = bblock['schema']['application/yaml']
    # r = requests.get(schema_url)
    # r.raise_for_status()
    # schema = r.text

    r = requests.get(bblock['documentation']['json-full']['url'])
    r.raise_for_status()
    bblock = r.json()

    r = requests.get(bblock['ldContext'])
    r.raise_for_status()
    ld_context = r.json()

    steps = bblock.get('semanticUplift', {}).get('additionalSteps', [])
    for step in steps:
        if not step.get('code') and step.get('ref'):
            r = requests.get(step['ref'])
            r.raise_for_status()
            step['code'] = r.text

    return schema_url, steps, ld_context


def compile_rule(register_url: str, bblock_id: str, input_data: str) -> Graph:
    schema_url, steps, ld_context = fetch_bblock(register_url, bblock_id)

    if isinstance(input_data, str):
        input_data = json.loads(input_data)

    validator = jsonschema.Draft202012Validator({'$ref': schema_url}, registry=schema_registry)
    validator.validate(input_data)

    for step in steps:
        if step['type'] == 'jq':
            input_data = jq.compile(step['code']).input_value(input_data).first()

    jsonld_data = {**ld_context, **input_data}
    g = Graph().parse(data=json.dumps(jsonld_data), format='json-ld')
    return g
