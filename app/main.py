import logging
from contextlib import asynccontextmanager
from typing import Annotated, Union

from fastapi import FastAPI, Request, HTTPException, Response, BackgroundTasks, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app import model, util
from app.config import settings
from app.jobs import job_executor
from app.profiles import ProfileLoader, ProfileList

MEDIA_TEXT_HTML = 'text/html'
MEDIA_APPLICATION_JSON = 'application/json'
MEDIA_ANY = '*/*'

app_metadata = {
    'title': 'CHEK data completeness service',
    'description': 'TBD',
    'version': '0.1',
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.profile_loader = ProfileLoader(settings.data_source)
    yield
    app.profile_loader.close()


app = FastAPI(
    **app_metadata,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.profile_loader = None

logger = logging.getLogger('uvicorn.error')


@app.get('/', response_model=model.LandingPage)
def capabilities(req: Request, accept: Annotated[str | None, Header()] = None) -> model.LandingPage | HTMLResponse:
    try:
        req_media_type = util.match_accept_header(accept, [MEDIA_TEXT_HTML, MEDIA_APPLICATION_JSON])
    except Exception as e:
        req_media_type = MEDIA_TEXT_HTML
        logger.error(f'Error parsing Accept header "{accept}"', e)

    if req_media_type is None:
        raise HTTPException(
            status_code=400,
            detail=model.Exception(
                type='UnsupportedMediaType',
                status=400,
                title='Unsupported media type',
            ).model_dump(exclude_none=True))

    if req_media_type == MEDIA_TEXT_HTML:
        return templates.TemplateResponse(request=req, name='index.j2')

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
            ).model_dump(exclude_none=True))

    process_description = profile.to_process_description()

    return process_description.model_dump(by_alias=True, exclude_unset=True)


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
            ).model_dump(exclude_none=True))

    parameters = {k: v for k, v in data.inputs.model_dump().items() if k != 'cityFiles'}
    job = job_executor.create_job(city_files=data.inputs.cityFiles,
                                  profiles=[profile],
                                  parameters=parameters,
                                  profile_loader=app.profile_loader)
    job_id = job.job_id
    background_tasks.add_task(job.execute_sync)

    resp.headers['Location'] = str(req.url_for('view_job', job_id=job_id))
    resp.headers['Preference-Applied'] = 'async-execute'
    return model.StatusInfo(
        processID=process_id,
        jobID=job_id,
        status=job.status,
        type=model.Type.process,
        created=job.created,
        started=job.started,
        finished=job.finished,
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
            ).model_dump(exclude_none=True))
    return model.StatusInfo(
        processID=','.join(p.get_id() for p in job.profiles),
        jobID=job_id,
        status=job.status,
        type=model.Type.process,
        created=job.created,
        started=job.started,
        finished=job.finished,
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
            ).model_dump(exclude_none=True))

    if job.status in (model.StatusCode.running, model.StatusCode.accepted):
        raise HTTPException(
            status_code=404,
            detail=model.Exception(
                type="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/result-not-ready",
                status=404,
                title='Result not ready',
            ).model_dump(exclude_none=True))

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
