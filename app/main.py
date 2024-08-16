from fastapi import FastAPI, Request, HTTPException, Response, BackgroundTasks
from fastapi.encoders import jsonable_encoder

from app import model
from app.config import settings
from app.jobs import job_executor
from app.profiles import ProfileLoader, ProfileList

app_metadata = {
    'title': 'CHEK data completeness service',
    'description': 'TBD',
    'version': '0.1',
}

app = FastAPI(
    **app_metadata
)

app.profile_loader = None


@app.on_event("startup")
def initialize():
    app.profile_loader = ProfileLoader(settings.data_source)


@app.on_event("shutdown")
def shutdown():
    app.profile_loader.close()


@app.get('/')
def capabilities(req: Request) -> model.LandingPage:
    return model.LandingPage(
        title=app_metadata['title'],
        description=app_metadata['description'],
        links=[
            model.Link(rel='self',
                       href=str(req.url),
                       type='application/json'),
            model.Link(rel='service-desc',
                       href=f"{req.base_url}openapi.json",
                       type='application/json'),
            model.Link(rel='service-doc',
                       href=f"{req.base_url}docs",
                       type='text/html'),
            model.Link(rel='http://www.opengis.net/def/rel/ogc/1.0/conformance',
                       href=str(req.url_for('conformance'))),
            model.Link(rel='http://www.opengis.net/def/rel/ogc/1.0/processes',
                       href=str(req.url_for('list_processes'))),
        ])


@app.get('/conformance')
def conformance() -> model.ConfClasses:
    return model.ConfClasses(conformsTo=[
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json',
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/ogc-process-description',
    ])


@app.get('/processes')
def list_processes() -> model.ProcessList:
    return model.ProcessList(
        processes=[profile.to_process_summary() for profile in app.profile_loader.profiles.values()],
        links=[],
    )


@app.get('/processes/{process_id}')
def view_process(process_id: str) -> model.Process:
    profile = app.profile_loader.profiles.get(process_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=model.Exception(
                type="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
                status=404,
                title='Process not found',
            ).dict(exclude_none=True))
    return profile.to_process_description()


@app.post('/processes/{process_id}/execution', status_code=201)
def process_execution(process_id: str, data: model.ValidationExecute, req: Request, resp: Response,
                      background_tasks: BackgroundTasks) -> model.StatusInfo:
    profile = app.profile_loader.profiles.get(process_id)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail=model.Exception(
                type="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
                status=404,
                title='Process not found',
            ).dict(exclude_none=True))

    job = job_executor.create_job(city_files=data.inputs.cityFiles, profile_loader=app.profile_loader)
    job_id = job.job_id
    background_tasks.add_task(job.execute_sync, [profile])

    resp.headers['Location'] = str(req.url_for('view_job', job_id=job_id))
    resp.headers['Preference-Applied'] = 'async-execute'
    return model.StatusInfo(
        processID=process_id,
        jobID=job_id,
        status=job.status,
        type=model.Type.process,
    )


@app.get('/jobs/{job_id}')
def view_job(job_id: str) -> model.StatusInfo:
    job = job_executor.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=model.Exception(
                type="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job",
                status=404,
                title='Job not found',
            ).dict(exclude_none=True))
    return model.StatusInfo(
        jobID=job_id,
        status=job.status,
        type=model.Type.process,
    )


@app.get('/jobs/{job_id}/results')
def job_results(job_id: str):
    job = job_executor.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=model.Exception(
                type="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job",
                status=404,
                title='Job not found',
            ).dict(exclude_none=True))

    if job.errors:
        return {
            'valid': False,
            'errors': [str(e) for e in job.errors],
        }
    else:
        result = {
            'valid': job.valid,
            'val3dityResult': job.val3dity_result,
            'shaclResult': job.shacl_result,
            'shaclReport': job.shacl_report,
            'fileValidation': [
                {
                    'fileIndex': file_result.index,
                    'name': file_result.input_file.name,
                    'valid': file_result.valid,
                    'val3dityReport': file_result.val3dity_report,
                }
                for file_result in job.city_files
            ],
        }
        if job.warnings:
            result['warnings'] = job.warnings
        return result


@app.get('/profiles')
def get_profiles() -> ProfileList:
    return ProfileList(app.profile_loader.profiles.values())
