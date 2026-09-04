"""ARQ worker entrypoint (V2 R2-1).

Main worker: run with `arq app.workers.main.WorkerSettings` for IO-bound jobs
(email, LMS sync, inventory reminders, etc.). This worker uses arq's default
concurrency (10) for short, IO-bound work.

Video worker: run with `arq app.workers.main.VideoWorkerSettings` for CPU-bound
transcoding. Single-concurrency to avoid saturating the VPS's 4 vCPUs; jobs
land on a separate Redis queue so long transcodes don't block other tasks.

`functions` and `cron_jobs` are registries other V2 tasks append to as they
land (R2-2's import-batch email job, later phases' scheduled jobs) — don't
replace these lists, extend them.
"""

from arq import cron, func

from app.workers.heartbeat import heartbeat
from app.workers.settings import redis_settings
from app.workers.tasks.cohort_interest import send_cohort_interest_notifications
from app.workers.tasks.imports import send_import_batch_emails
from app.workers.tasks.inventory import send_inventory_reminders
from app.workers.tasks.lms import sync_import_batch_lms_accounts, sync_registration_lms_job
from app.workers.tasks.staffing import send_assignment_email, send_call_invite_emails
from app.workers.tasks.tickets import send_ticket_email
from app.workers.tasks.video import transcode_video


class WorkerSettings:
    redis_settings = redis_settings()
    functions = [
        send_ticket_email,
        send_import_batch_emails,
        send_assignment_email,
        send_call_invite_emails,
        send_inventory_reminders,
        # arq's default job_timeout is 300s — fine for every other job here.
        # transcode_video is CPU-bound and runs long; it's on a separate queue
        # with max_jobs=1 (see VideoWorkerSettings below) to avoid blocking
        # IO-bound work like email and LMS sync (finding #2).
        sync_import_batch_lms_accounts,
        sync_registration_lms_job,
        send_cohort_interest_notifications,
    ]
    cron_jobs = [
        cron(heartbeat, minute=set(range(0, 60, 5)), run_at_startup=True),
        # Once a day, mid-morning local time. Not hourly: a reminder that
        # arrives repeatedly is one people learn to ignore, and neither of
        # these situations changes fast enough to warrant it (I2-5).
        cron(send_inventory_reminders, hour={6}, minute={0}),
    ]


class VideoWorkerSettings:
    redis_settings = redis_settings()
    queue_name = "arq:queue:video"
    functions = [
        # CPU-bound HLS transcode with 3600s timeout (ffmpeg on a VPS takes time).
        # Kept on a separate queue and worker to avoid blocking IO-bound jobs like
        # email and LMS sync. max_jobs=1 prevents concurrent transcodes from
        # saturating all 4 vCPUs (finding #2).
        func(transcode_video, timeout=3600),
    ]
    max_jobs = 1
