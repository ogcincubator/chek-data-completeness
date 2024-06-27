from app import model

PROCESS_SUMMARY = model.ProcessSummary(
    id='validate',
    version='0.1',
    jobControlOptions=[model.JobControlOptions.async_execute],
)
PROCESS_DESCRIPTION = model.Process(
    **PROCESS_SUMMARY.dict(),
)
