import datetime
import random
import os
from dash import CeleryManager
from celery import Celery
import time
import redis
import json

REDIS_URL = os.environ.get("REDIS_URL")
celery_app = Celery(
    "Celery App", broker=f"{REDIS_URL}/2", backend=f"{REDIS_URL}/3"
)
background_callback_manager = CeleryManager(celery_app)

# DB to store the values - we define different numbers like f"{REDIS_URL}/1"
# because we are using different redis partitions for different purposes
redis_store = redis.StrictRedis.from_url(f"{REDIS_URL}/1")

# function to retrieve the data from the DB, cna be used in regular callbacks and outside callbacks too
def retrieve_data_from_db(as_str=False):
    data = redis_store.hget("app-data", "DATASET") 
    if not data :
        return "[]" if as_str else []
    else :
        return data if as_str else json.loads(data)

# raw function that will take a long time
# we define it without the decorator so that we can use it inside the background callback
# if you're not going to use it inside the background callback, you could define it with the @celery_app.task decorator directly
def mytask_unwrapped(N=1, sleep_time=10):

    # simulating long-running process
    time.sleep(sleep_time)

    new_values = [
        {
            "creation_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "col_numeric": random.randint(0, 200),
            "col_category": random.choice(["A", "B", "C", "D"]),
        }
        for i in range(N)
    ]

    # this is not the most efficient 
    # in a real-case scenario you'd have a Postgres DB and would append new values instead of rewritting everything
    existing_values = retrieve_data_from_db()
    all_values = existing_values + new_values
    redis_store.hset("app-data", "DATASET", json.dumps(all_values))

    return new_values

# we call the raw mytask_unwrapped function inside a celery task so that it's sent to the queue
@celery_app.task(name="add_new_value")
def mytask_wrapped(**kwargs):
    mytask_unwrapped(**kwargs)
    return

# this way of specifying the schedule will NOT work if we are using the same celery_app object for bg callbacks and celery tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # This command invokes a celery task at an interval of every 90 seconds (3min). You can change this.
    # since we are not passing arguments to mytask, it will run with the default values
    sender.add_periodic_task(5, mytask_wrapped.s(), name="Scheduled update")

# celery_app.conf.beat_schedule = {
#     'Scheduled update': {
#         'task': 'add_new_value', # task name
#         'schedule': 90.0,
#     },
# }