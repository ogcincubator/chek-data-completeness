import dataclasses
import datetime
import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import List, Any

from pyld import jsonld
from rdflib import Graph, BNode, RDF, Namespace, DCTERMS, Literal

from app import model, util, profiles, rule_template
from app.profiles import Profile, ProfileLoader
from app.config import settings
import uuid
import shutil
import subprocess

MAX_JOBS = 100

SHACL_RESULT_FRAME = json.loads('''
{
    "@context": {
        "shacl": "http://www.w3.org/ns/shacl#",
        "@vocab": "http://www.w3.org/ns/shacl#",
        "result": {
            "@container": "@set"
        },
        "focusNode": {
            "@type": "@id"
        },
        "resultPath": {
            "@type": "@id",
            "@container": "@set"
        },
        "resultSeverity": {
            "@type": "@id"
        }
    },
    "@type": "http://www.w3.org/ns/shacl#ValidationReport"
}
''')

SD = Namespace('https://w3id.org/okn/o/sd#')


@dataclasses.dataclass
class FileResult:
    index: int
    path: Path
    is_cityjson: True
    input_file: model.InputFile
    val3dity_report: Any = None

    @property
    def valid(self):
        if not self.val3dity_report:
            return True
        return self.val3dity_report.get('validity', True)


class Job:
    def __init__(self,
                 job_id: str,
                 parameters: dict[str, str | int | float | bool] = None,
                 *args, **kwargs):
        self.created = datetime.datetime.now(datetime.timezone.utc)
        self.started = None
        self.finished = None

        self.parameters = parameters
        self._process_id = kwargs.pop('process_id', None)
        self.args = args
        self.kwargs = kwargs

        self.job_id = job_id
        self.status = model.StatusCode.accepted
        self.errors = []
        self.warnings = []
        self.wd = Path(settings.temp_dir, self.job_id[0:2], self.job_id)
        self.wd.mkdir(exist_ok=False, parents=True)

    @property
    def valid(self):
        return len(self.errors) == 0

    def clean(self):
        shutil.rmtree(self.wd)

    def execute_sync(self):
        self.started = datetime.datetime.now(datetime.timezone.utc)
        self.status = model.StatusCode.running
        try:
            self.execute_inner()
            self.status = model.StatusCode.successful
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.errors.append(e)
            self.status = model.StatusCode.failed

        finally:
            self.finished = datetime.datetime.now(datetime.timezone.utc)


    def execute_inner(self):
        # noop
        pass

    def get_result(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            'valid': self.valid,
        }
        if self.warnings:
            result['warnings'] = self.warnings
        return result

    @property
    def process_id(self):
        return self._process_id or 'GenericJob'

class ProfileJob(Job):

    def __init__(self,
                 job_id: str,
                 city_files: list[model.InputFile] | None = None,
                 parameters: dict[str, str | int | float | bool] = None,
                 profiles: List[Profile] | None = None,
                 profile_loader: ProfileLoader | None = None,
                 *args, **kwargs):

        super().__init__(job_id, parameters=parameters)

        self.profile_loader = profile_loader

        self.is_direct_validator = kwargs.get('profile_id') == '_shaclValidation'

        self.val3dity_result = True
        self.shacl_result = True
        self.shacl_report = ''

        self.profiles = profiles
        self.city_files: list[FileResult] = []

        for i, city_file in enumerate(city_files):
            output_fn = self.wd / f"input_city.{i}.json"
            is_cityjson = True
            if util.is_xml(city_file.data_str):
                # Convert to CityJSON
                output_fn = output_fn.with_suffix('.gml')
                is_cityjson = False

            city_file.write_to(output_fn)
            self.city_files.append(FileResult(
                index=i,
                path=output_fn,
                input_file=city_file,
                is_cityjson=is_cityjson,
            ))

    def execute_inner(self):

        # 1. Fetch SHACL rules
        shacl_filename = self.wd / "shacl.ttl"
        if self.is_direct_validator:
            with open(shacl_filename, 'w') as f:
                f.write(self.parameters.pop('shacl'))
        else:
            loaded_profile_uris = set()
            pending_profiles = deque(self.profiles)
            shacl_graph = Graph()
            while pending_profiles:
                profile = pending_profiles.popleft()
                if profile.uri in loaded_profile_uris:
                    continue
                for resource in profile.resources:
                    if (resource.role != 'prof-role:validation'
                            or resource.conformsTo != 'https://www.w3.org/TR/shacl/'):
                        continue
                    for artifact in resource.artifacts:
                        public_id = 'urn:check:shacl/doc' if not re.match(r'^https?://', artifact) else artifact
                        shacl_graph.parse(artifact, format='ttl', publicID=public_id)
                for profile_of_uri in profile.profileOf:
                    if profile_of_uri in loaded_profile_uris or profile_of_uri in ('urn:chek:profiles/chek',
                                                                                   'chekp:chek'):
                        continue
                    profile_of = None
                    if self.profile_loader:
                        profile_of = self.profile_loader.profiles_by_uri.get(profile_of_uri)
                    if profile_of:
                        pending_profiles.append(profile_of)
                    else:
                        self.warnings.append({
                            'type': 'ProfileNotFound',
                            'uri': profile_of_uri,
                            'message': f"Profile {profile_of_uri} not found",
                        })
                loaded_profile_uris.add(profile.uri)

            shacl_graph.serialize(shacl_filename)

        # 2. Convert to CityJSON
        for city_file in self.city_files:
            if not city_file.is_cityjson:
                subprocess_result = subprocess.run(
                    [
                        settings.citygml_tools,
                        'to-cityjson',
                        str(city_file.path),
                    ],
                    capture_output=True,
                    text=True,
                )
                if subprocess_result.returncode:
                    errors = subprocess_result.stderr
                    errors += '\n'.join(line
                                        for line in subprocess_result.stdout.splitlines()
                                        if 'ERROR]' in line)
                    raise Exception(f"Error converting input file {city_file.index} to CityJSON: {errors}")
                city_file.path = city_file.path.with_suffix('.json')
                city_file.is_cityjson = True

        # 3. Run validation
        ttl_files = []
        for city_file in self.city_files:
            path = city_file.path
            # 3.1 val3dity
            report_fn = path.with_name(path.stem + '-val3dity.json')
            subprocess.run(
                [
                    settings.val3dity,
                    '--report',
                    str(report_fn),
                    str(path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).check_returncode()
            with open(report_fn) as f:
                val3dity_report = json.load(f)
            self.val3dity_result = self.val3dity_result and val3dity_report['validity']
            city_file.val3dity_report = val3dity_report

            # 3.2 Uplift
            ttl_pre_file = path.with_name(path.stem + '-uplift-pre.ttl')
            subprocess_result = subprocess.run(
                [
                    'python3',
                    '-m',
                    'ogc.na.ingest_json',
                    '--transform-arg',
                    f'file_idx={city_file.index}',
                    '--no-provenance',
                    '--ttl',
                    '--ttl-file',
                    str(ttl_pre_file),
                    '--context',
                    './data/cityjson-uplift.yml',
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if subprocess_result.returncode:
                print(subprocess_result.stdout, file=sys.stderr)
                raise Exception(f"Error converting input file {city_file.index} to RDF")

            ttl_file = path.with_name(path.stem + '-uplift.ttl')
            subprocess_result = subprocess.run(
                [
                    'python3',
                    './app/entail.py',
                    str(ttl_pre_file),
                    './data/cityjson-entailments.shacl',
                    str(ttl_file),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if subprocess_result.returncode:
                print(subprocess_result.stdout, file=sys.stderr)
                raise Exception(f"Error applying inference to input file {city_file.index}")

            ttl_files.append(ttl_file)

        # 4. Append variables
        if self.parameters:
            param_g = Graph()
            param_g.bind('sd', SD)
            for k, v in self.parameters.items():
                param_node = BNode()
                param_g.add((param_node, RDF.type, SD.Parameter))
                param_g.add((param_node, DCTERMS.identifier, Literal(k)))
                param_g.add((param_node, SD.hasFixedValue, Literal(v)))
            param_ttl_file = self.wd / 'shacl-params.ttl'
            param_g.serialize(param_ttl_file)
            ttl_files.append(param_ttl_file)

        # 5. Concatenate TTL files
        output_ttl_file = self.wd / 'city.ttl'
        util.concat_files(ttl_files, output_ttl_file)

        # 5. SHACL
        shacl_output = output_ttl_file.with_name('city-shacl-result.json')
        shacl_process = subprocess.run(
            [
                'python3',
                './app/shacl_validate.py',
                str(output_ttl_file),
                str(shacl_filename),
                str(shacl_output),
            ],
            capture_output=True,
            text=True
        )
        self.shacl_result = shacl_process.returncode == 0
        if self.shacl_result:
            with open(shacl_output) as f:
                shacl_report_text = f.read()
            try:
                self.shacl_report = jsonld.frame(json.loads(shacl_report_text), SHACL_RESULT_FRAME)
            except Exception as e:
                raise Exception(f'Error running SHACL validation: {shacl_report_text}') from e
        else:
            raise Exception(f'Error running SHACL validation: {shacl_process.stderr}')

        self.status = model.StatusCode.successful

    @property
    def valid(self):
        return len(self.errors) == 0 and self.shacl_result and self.val3dity_result

    def get_result(self):
        result = super().get_result()
        result.update({
            'val3dityResult': self.val3dity_result,
            'shaclResult': self.shacl_result,
            'shaclReport': self.shacl_report,
            'fileValidation': [
                {
                    'fileIndex': file_result.index,
                    'name': file_result.input_file.name,
                    'valid': file_result.valid,
                    'val3dityReport': file_result.val3dity_report,
                }
                for file_result in self.city_files
            ],
        })
        return result

    @property
    def process_id(self):
        return ','.join(p.get_id() for p in self.profiles) if self.profiles else super().process_id


class SemanticUpliftJob(Job):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        city_file : model.InputFile = self.kwargs.get('city_files')[0]
        output_fn = self.wd / f"input_city.0.json"
        is_cityjson = True
        if util.is_xml(city_file.data_str):
            # Convert to CityJSON
            output_fn = output_fn.with_suffix('.gml')
            is_cityjson = False
        city_file.write_to(output_fn)
        self.city_file = FileResult(
            index=0,
            path=output_fn,
            input_file=city_file,
            is_cityjson=is_cityjson,
        )
        self.path = self.city_file.path

        self.output_file = None

    def execute_inner(self):
        rdf_format = self.parameters.get('outputFormat', 'ttl')
        city_file = self.city_file

        # 1. Convert to CityJSON
        if not city_file.is_cityjson:
            subprocess_result = subprocess.run(
                [
                    settings.citygml_tools,
                    'to-cityjson',
                    str(city_file.path),
                ],
                capture_output=True,
                text=True,
            )
            if subprocess_result.returncode:
                errors = subprocess_result.stderr
                errors += '\n'.join(line
                                    for line in subprocess_result.stdout.splitlines()
                                    if 'ERROR]' in line)
                raise Exception(f"Error converting input file {city_file.index} to CityJSON: {errors}")
            city_file.path = city_file.path.with_suffix('.json')
            city_file.is_cityjson = True

        # 2. Uplift
        apply_entailments = True
        if rdf_format in ('jsonld', 'json-ld', 'application/ld+json'):
            params = ['--json-ld', '--json-ld-file', '-uplift.jsonld']
            apply_entailments = False
        elif rdf_format in ('ttl', 'turtle', 'text/turtle'):
            params = ['--ttl', '--ttl-file', '-uplift.ttl']
        else:
            raise ValueError(f"Unsupported format: {rdf_format}")
        self.output_file = self.path.with_name(self.path.stem + params[2])
        params[2] = (str(self.output_file.with_stem('-pre' + self.output_file.stem))
                     if apply_entailments
                     else str(self.output_file))
        subprocess_result = subprocess.run(
            [
                'python3',
                '-m',
                'ogc.na.ingest_json',
                '--transform-arg',
                f'file_idx={city_file.index}',
                '--no-provenance',
                ] + params + [
                '--context',
                './data/cityjson-uplift.yml',
                city_file.path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if subprocess_result.returncode:
            print(subprocess_result.stdout, file=sys.stderr)
            raise Exception(f"Error converting input file {city_file.index} to RDF")

        if apply_entailments:
            subprocess_result = subprocess.run(
                [
                    'python3',
                    './app/entail.py',
                    params[2],
                    './data/cityjson-entailments.shacl',
                    str(self.output_file),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if subprocess_result.returncode:
                print(subprocess_result.stdout, file=sys.stderr)
                raise Exception(f"Error applying inference to input file {city_file.index}")

    def get_result(self):
        result = super().get_result()
        if self.valid:
            with open(self.output_file) as f:
                data = f.read()
            result.update({
                'filename': self.output_file.name,
                'data': data,
            })
        return result

    @property
    def process_id(self):
        return '_semanticUplift'


class CityGML2CityJSONJob(Job):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        city_file : model.InputFile = self.kwargs.get('city_files')[0]
        output_fn = self.wd / f"input_city.0.gml"
        city_file.write_to(output_fn)
        self.city_file = FileResult(
            index=0,
            path=output_fn,
            input_file=city_file,
            is_cityjson=False,
        )
        self.path = self.city_file.path

        self.output_file = None

    def execute_inner(self):
        city_file = self.city_file

        # Convert to CityJSON
        subprocess_result = subprocess.run(
            [
                settings.citygml_tools,
                'to-cityjson',
                str(city_file.path),
            ],
            capture_output=True,
            text=True,
        )
        if subprocess_result.returncode:
            errors = subprocess_result.stderr
            errors += '\n'.join(line
                                for line in subprocess_result.stdout.splitlines()
                                if 'ERROR]' in line)
            raise Exception(f"Error converting input file {city_file.index} to CityJSON: {errors}")
        self.output_file = city_file.path.with_suffix('.json')

    def get_result(self):
        result = super().get_result()
        if self.valid:
            with open(self.output_file) as f:
                data = f.read()
            result.update({
                'filename': self.output_file.name,
                'data': data,
            })
        return result

    @property
    def process_id(self):
        return '_semanticUplift'


class RuleTemplateJob(Job):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.input_json = self.parameters.get('inputJson')
        self.bblock_id = self.parameters.get('bblockId')
        self.ttl_result = None

    def execute_inner(self):
        g = rule_template.compile_rule(
            'https://ogcincubator.github.io/chek-profiles-bblocks/build/register.json',
            self.bblock_id,
            self.input_json,
        )
        self.ttl_result = g.serialize(format='ttl')

    def get_result(self):
        result = super().get_result()
        result['valid'] = self.ttl_result is not None
        result['data'] = self.ttl_result
        return result

    @property
    def process_id(self):
        return '_citygml2cityjson'


RESERVED_PROCESSES = {
    '_semanticUplift': {
        'process': model.Process(
            id='_semanticUplift',
            version='0.1',
            title='Semantic Uplift',
            description='Semantic Uplift from CityJSON/CityGML documents',
            inputs={
                'cityFiles': profiles.COMMON_INPUTS['cityFiles'],
                'outputFormat': model.InputDescription(
                    schema=model.Schema(
                        type='string',
                        title='RDF Format',
                    ),
                ),
            },
        ),
        'class': SemanticUpliftJob,
    },
    '_ruleTemplate': {
        'process': model.Process(
            id='_ruleTemplate',
            version='0.1',
            title='Rule template',
            description='Rule template uplift',
            inputs={
                'inputJson': model.InputDescription(
                    schema=model.Schema(
                        type='string',
                        title='Input JSON as string',
                    ),
                ),
                'bblockId': model.InputDescription(
                    schema=model.Schema(
                        type='string',
                        title='Template building block id',
                    ),
                ),
            },
        ),
        'class': RuleTemplateJob,
    },
    '_shaclValidation': {
        'process': model.Process(
            id='_shaclValidation',
            version='0.1',
            title='SHACL validation',
            description='Direct SHACL validation of CityJSON/CityGML documents (without using profiles)',
            inputs={
                'cityFiles': profiles.COMMON_INPUTS['cityFiles'],
                'shacl': model.InputDescription(
                    schema=model.Schema(
                        type='string',
                        title='SHACL shapes in RDF/Turtle format',
                    ),
                ),
            },
        ),
        'class': ProfileJob,
    },
    '_citygml2cityjson': {
            'process': model.Process(
                id='_citygml2cityjson',
                version='0.1',
                title='CityGML to CityJSON',
                description='Converts CityGML to CityJSON using citygml-tools',
                inputs={
                    'cityFiles': profiles.COMMON_INPUTS['cityFiles'],
                },
            ),
            'class': CityGML2CityJSONJob,
        },
}

class JobExecutor:

    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def create_job(self, profile_ids: list[str],
                   profile_loader: ProfileLoader,
                   city_files: list[model.InputFile] | None = None,
                   parameters: dict[str, str | int | float | bool] = None):
        job_id = str(uuid.uuid4())
        job = None
        for req_profile in profile_ids:
            if req_profile in RESERVED_PROCESSES:
                job = RESERVED_PROCESSES[req_profile]['class'](job_id,
                                                               city_files=city_files,
                                                               parameters=parameters,
                                                               profile_id=req_profile)
                break
        if not job:
            profiles = [profile_loader.profiles[pid] for pid in profile_ids]
            job = ProfileJob(job_id, city_files, profiles=profiles, parameters=parameters, profile_loader=profile_loader)
        self.jobs[job_id] = job

        # Remove old jobs
        while len(self.jobs) >= MAX_JOBS:
            self.jobs.pop(next(iter(self.jobs))).clean()

        return job

    def get_job(self, job_id) -> Job | None:
        return self.jobs.get(job_id)


job_executor = JobExecutor()
