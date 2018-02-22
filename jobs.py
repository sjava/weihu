from apscheduler.schedulers.blocking import BlockingScheduler
from bras import add_bingfa, add_itv_online
import switch
import olt

sched = BlockingScheduler(daemonic=False)


def bas_add_bingfa():
    add_bingfa()


def olt_tuopu():
    olt.del_old_data()
    olt.add_infs()
    olt.add_groups()


def sw_tuopu():
    switch.update_model()
    switch.del_old_data()

    switch.add_groups()
    switch.add_infs()
    switch.add_traffics()


def xunjian():
    olt.add_main_card()
    olt.add_power_info()
    switch.add_main_card()
    switch.add_power_info()


def itv_online():
    add_itv_online()


sched.add_job(bas_add_bingfa, 'cron', day_of_week='0-6', hour='6', minute='15')
sched.add_job(
    itv_online, 'cron', day_of_week='0-6', hour='18-24', minute='*/15')
# sched.add_job(sw_tuopu, 'cron',
#              day_of_week='0-6', hour='20', minute='00')
# sched.add_job(sw_tuopu, 'cron', day_of_week='0-6', hour='21', minute='00')
# sched.add_job(olt_tuopu, 'cron', day_of_week='0-6', hour='20', minute='30')
# sched.add_job(xunjian, 'cron', day_of_week='0', hour='1', minute='30')
#  sched.add_job(sw_add_traffics, 'cron',
#  day_of_week='0-6', hour='18-22', minute='20/15')
try:
    sched.start()
except (KeyboardInterrupt, SystemExit):
    pass
