from fastapi import FastAPI, Request
from app import model

app_metadata = {
    'title': 'CHEK data completeness service',
    'description': 'TBD',
    'version': '0.1',
}

app = FastAPI(
    **app_metadata
)


@app.get('/')
def capabilities(req: Request):
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
                       href=str(req.url_for('processes'))),
        ])


@app.get('/conformance')
def conformance():
    return model.ConfClasses(conformsTo=[
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json',
        'http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/ogc-process-description',
    ])


@app.get('/processes')
def processes():
    pass


@app.get('/processes/{process_id}')
def process():
    pass


@app.post('/process/{process_id}/execution')
def process_execution():
    pass


@app.get('/jobs/{job_id}')
def job():
    pass


@app.get('/jobs/{job_id}/results')
def job_results():
    pass
