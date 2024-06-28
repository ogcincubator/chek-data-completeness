import dataclasses
import json
import re
from pathlib import Path
from typing import List, Any

from ogc.na.ingest_json import uplift_json
from pyld import jsonld
from rdflib import Graph

from app import model
from app.profiles import Profile
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


@dataclasses.dataclass
class FileResult:
    path: Path
    input_file: model.InputFile
    val3dity_report: Any = None
    shacl_report: Any = None
    valid: bool = True


class Job:

    def __init__(self, job_id: str, city_files: list[model.InputFile]):
        self.job_id = job_id
        self.status = model.StatusCode.accepted
        self.errors = []
        self.wd = Path(settings.temp_dir, self.job_id)
        self.wd.mkdir(exist_ok=False, parents=True)

        self.val3dity_result = True
        self.shacl_result = True

        self.city_files: list[FileResult] = []

        for i, city_file in enumerate(city_files):
            # TODO: CityGML support
            output_fn = self.wd / f"input_city.{i}.json"
            with open(output_fn, 'w') as f:
                f.write(city_file.data_str)
            self.city_files.append(FileResult(
                path=output_fn,
                input_file=city_file,
            ))

    def clean(self):
        shutil.rmtree(self.wd)

    def execute_sync(self, profiles: List[Profile]):

        self.status = model.StatusCode.running
        try:
            # 1. Fetch SHACL rules
            shacl_graph = Graph()
            # TODO: isProfileOf
            for profile in profiles:
                for resource in profile.resources:
                    for artifact in resource.artifacts:
                        public_id = 'urn:check:shacl/doc' if not re.match(r'^https?://', artifact) else artifact
                        shacl_graph.parse(artifact, publicID=public_id)
            shacl_filename = self.wd / "shacl.ttl"
            shacl_graph.serialize(shacl_filename)

            # 2. Convert to CityJSON
            # TODO

            for city_file in self.city_files:
                path = city_file.path
                # 2. Check geometry with val3dity
                report_fn = path.with_name(path.stem + '-val3dity.json')
                subprocess.run([
                    settings.val3dity,
                    '--report',
                    str(report_fn),
                    str(path),
                ])
                with open(report_fn) as f:
                    val3dity_report = json.load(f)
                self.val3dity_result = self.val3dity_result and val3dity_report['validity']
                city_file.val3dity_report = val3dity_report

                # 3. Uplift
                ttl_file = path.with_name(path.stem + '-uplift.ttl')
                subprocess.run([
                    'python',
                    '-m',
                    'ogc.na.ingest_json',
                    '--no-provenance',
                    '--ttl',
                    '--ttl-file',
                    str(ttl_file),
                    '--context',
                    './data/cityjson-uplift.yml',
                    str(path),
                ])

                # 4. Append variables
                # TODO

                # 5. Validate
                shacl_output = path.with_name(path.stem + '-shacl-result.txt')
                shacl_process = subprocess.run([
                    'pyshacl',
                    '-s',
                    str(shacl_filename),
                    '-f',
                    'json-ld',
                    '-o',
                    str(shacl_output),
                    str(ttl_file),
                ])
                self.shacl_result = self.shacl_result and shacl_process.returncode == 0
                with open(shacl_output) as f:
                    city_file.shacl_report = jsonld.frame(json.load(f), SHACL_RESULT_FRAME)

                city_file.valid = val3dity_report['validity'] and shacl_process.returncode == 0

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

    def create_job(self, city_files: list[model.InputFile]):
        job_id = str(uuid.uuid4())
        job = Job(job_id, city_files)
        self.jobs[job_id] = job

        # Remove old jobs
        while len(self.jobs) >= MAX_JOBS:
            self.jobs.pop(next(iter(self.jobs))).clean()

        return job

    def get_job(self, job_id) -> Job | None:
        return self.jobs.get(job_id)


job_executor = JobExecutor()
