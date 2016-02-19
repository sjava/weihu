from apscheduler.schedulers.blocking import BlockingScheduler
from bras import add_bingfa
from switch import add_groups, add_infs, add_traffics

sched = BlockingScheduler(daemonic=False)


def bas_add_bingfa():
    add_bingfa()


def sw_add_tuopu():
    add_groups()
    add_infs()
    add_traffics()


def sw_add_traffics():
    add_traffics()


sched.add_job(bas_add_bingfa, 'cron',
              day_of_week='0-6', hour='6', minute='15')
sched.add_job(sw_add_tuopu, 'cron',
              day_of_week='0-6', hour='20', minute='0')
#  sched.add_job(sw_add_traffics, 'cron',
#  day_of_week='0-6', hour='18-22', minute='20/15')
sched.start()
