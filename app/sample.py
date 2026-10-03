from .database import Meeting, Task


def sample_meeting():
    lines = [
        ('Nishan', 0, 36, 'Let’s review the release. The login refresh bug is blocking QA. We agreed to keep the release behind the feature flag until the authentication tests pass.'),
        ('Raghunandhan', 36, 74, 'I will fix the refresh token issue in the authentication module before Friday. The retry currently reuses an expired token. I will add a regression test with the fix.'),
        ('Prajjwal', 74, 112, 'I will implement rate limiting on the public API by Thursday. We decided on a limit of 100 requests per minute per API key, with a 429 response when exceeded.'),
        ('Sharvan', 112, 151, 'I will run the authentication regression suite after the token fix lands, before the release. I’ll document any remaining failures in the QA checklist.'),
        ('Nishan', 151, 183, 'Good. We also agreed to keep PostgreSQL as the source of truth for meeting history. We still need to investigate the audio upload timeout; no owner has been assigned yet.'),
    ]
    meeting = Meeting(title='Release readiness · Engineering sync', source='sample', status='ready', duration=183,
        transcript='\n'.join(f'{name}: {text}' for name, _, _, text in lines),
        segments=[{'speaker': n, 'start': s, 'end': e, 'text': t} for n, s, e, t in lines],
        summary='The team reviewed release readiness and identified the authentication refresh bug as the main blocker. Work was assigned for the token fix, API rate limiting, and regression testing. The release will remain behind a feature flag until authentication tests pass. The audio upload timeout remains an open investigation.',
        topics=['Release readiness', 'Authentication', 'API reliability'],
        decisions=['Keep the release behind a feature flag until authentication tests pass.', 'Limit the public API to 100 requests per minute per API key, returning HTTP 429 above that limit.', 'Use PostgreSQL as the source of truth for meeting history.'])
    meeting.tasks = [
        Task(position=0, title='Fix refresh token reuse in authentication', description='Replace the expired token on retry and add a regression test covering the refresh flow.', owner='Raghunandhan', due_date='Before Friday', priority='high', feature='Authentication', evidence='I will fix the refresh token issue in the authentication module before Friday.'),
        Task(position=1, title='Add rate limiting to the public API', description='Enforce 100 requests per minute per API key and return HTTP 429 above the limit.', owner='Prajjwal', due_date='By Thursday', priority='medium', feature='Public API', evidence='I will implement rate limiting on the public API by Thursday.'),
        Task(position=2, title='Run the authentication regression suite', description='Run the suite after the token fix lands and document remaining failures in the QA checklist.', owner='Sharvan', due_date='Before the release', priority='high', feature='Quality assurance', evidence='I will run the authentication regression suite after the token fix lands, before the release.'),
    ]
    return meeting
