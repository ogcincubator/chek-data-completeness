import dataclasses
import json
import re
from collections import deque
from pathlib import Path
from typing import List, Any

from pyld import jsonld
from rdflib import Graph, BNode, RDF, Namespace, DCTERMS, Literal

from app import model, util
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
    valid: bool = True


class Job:

    def __init__(self, job_id: str, city_files: list[model.InputFile],
                 profile_loader: ProfileLoader | None = None):
        self.job_id = job_id
        self.status = model.StatusCode.accepted
        self.errors = []
        self.warnings = []
        self.wd = Path(settings.temp_dir, self.job_id[0:2], self.job_id)
        self.wd.mkdir(exist_ok=False, parents=True)

        self.profile_loader = profile_loader

        self.val3dity_result = True
        self.shacl_result = True
        self.shacl_report = ''

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

    def clean(self):
        shutil.rmtree(self.wd)

    def execute_sync(self, profiles: List[Profile],
                     parameters: dict[str, str | int | float | bool] = None):

        self.status = model.StatusCode.running

        loaded_profile_uris = set()
        pending_profiles = deque(profiles)

        try:
            # 1. Fetch SHACL rules
            shacl_graph = Graph()
            while pending_profiles:
                profile = pending_profiles.popleft()
                for resource in profile.resources:
                    for artifact in resource.artifacts:
                        public_id = 'urn:check:shacl/doc' if not re.match(r'^https?://', artifact) else artifact
                        shacl_graph.parse(artifact, publicID=public_id)
                for profile_of_uri in profile.profileOf:
                    if profile_of_uri in loaded_profile_uris or profile_of_uri in ('urn:chek:profiles/chek',
                                                                                   'chekp:chek'):
                        continue
                    profile_of = None
                    if self.profile_loader:
                        profile_of = self.profile_loader.profiles_by_uri.get(profile_of_uri)
                    if profile_of:
                        pending_profiles.append(profile)
                    else:
                        self.warnings.append({
                            'type': 'ProfileNotFound',
                            'uri': profile_of_uri,
                            'message': f"Profile {profile_of_uri} not found",
                        })
                loaded_profile_uris.add(profile.uri)

            shacl_filename = self.wd / "shacl.ttl"
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
                ttl_file = path.with_name(path.stem + '-uplift.ttl')
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
                        str(ttl_file),
                        '--context',
                        './data/cityjson-uplift.yml',
                        str(path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                if subprocess_result.returncode:
                    raise Exception(f"Error converting input file {city_file.index} to RDF: {subprocess_result.stdout}")

                ttl_files.append(ttl_file)

            # 4. Append variables
            if parameters:
                param_g = Graph()
                param_g.bind('sd', SD)
                for k, v in parameters.items():
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
            shacl_process = subprocess.run([
                'pyshacl',
                '-s',
                str(shacl_filename),
                '-f',
                'json-ld',
                '-o',
                str(shacl_output),
                str(output_ttl_file),
            ])
            self.shacl_result = shacl_process.returncode == 0
            with open(shacl_output) as f:
                self.shacl_report = jsonld.frame(json.load(f), SHACL_RESULT_FRAME)

            self.status = model.StatusCode.successful

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.errors.append(e)
            self.status = model.StatusCode.failed

    @property
    def valid(self):
        return len(self.errors) == 0 and self.shacl_result and self.val3dity_result


class JobExecutor:

    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def create_job(self, city_files: list[model.InputFile], profile_loader: ProfileLoader | None = None):
        job_id = str(uuid.uuid4())
        job = Job(job_id, city_files, profile_loader=profile_loader)
        self.jobs[job_id] = job

        # Remove old jobs
        while len(self.jobs) >= MAX_JOBS:
            self.jobs.pop(next(iter(self.jobs))).clean()

        return job

    def get_job(self, job_id) -> Job | None:
        return self.jobs.get(job_id)


job_executor = JobExecutor()
