from apscheduler.schedulers.blocking import BlockingScheduler
from bras import bingfa_check

sched = BlockingScheduler(daemonic=False)


def bas_bingfa_check():
    bingfa_check()
sched.add_job(bas_bingfa_check, 'cron',
              day_of_week='0-4', hour='11', minute='10')
sched.start()
