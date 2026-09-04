"""ARQ worker entrypoint (V2 R2-1). Run with: arq app.workers.main.WorkerSettings

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
    # arq defaults to 10 concurrent jobs. Every other job here is IO-bound
    # (email, imports) and would be fine at that, but transcode_video is not:
    # one ffmpeg encode saturates all four of this box's vCPUs, and the API
    # shares them. Ten at once during a bulk re-encode would take the live
    # platform down with it, and even nice -n 19 does not help when every
    # runnable thread is an encode.
    #
    # Serial is also simply faster in wall-clock terms for CPU-bound work —
    # ten encodes time-slicing four cores finish no sooner than ten in a row,
    # they just all finish at the end instead of one at a time, so nothing is
    # watchable until the whole batch is done.
    max_jobs = 1
    functions = [
        send_ticket_email,
        send_import_batch_emails,
        send_assignment_email,
        send_call_invite_emails,
        send_inventory_reminders,
        # arq's default job_timeout is 300s — fine for every other job here,
        # but a real ffmpeg HLS encode of a few-hundred-MB video routinely
        # runs well past that on a VPS with no hardware encoding. Hit this
        # for real on the Introduction course import: everything over ~90MB
        # got killed mid-encode. Scoped to this one function so other jobs
        # keep the short default (a stuck email/import job should still be
        # caught quickly).
        func(transcode_video, timeout=3600),
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
