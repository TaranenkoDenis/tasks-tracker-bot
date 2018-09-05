import json
import logging
import logging.handlers
import time
from datetime import datetime

from singleton import db, bot

logger = logging.getLogger(__name__)


class Status:
    TODO = 'TODO'
    DO = 'DO'  # in progress
    DONE = 'DONE'
    ALL = (TODO, DO, DONE)


def init_log():
    handlers = [logging.StreamHandler()]

    # capture warnings, along with asyncio runtime warnings
    # e.g. RuntimeWaring: coroutine <X> was never awaited
    logging.captureWarnings(True)

    logging.basicConfig(
        format='%(levelname)-8s [%(asctime)s] %(message).1000s',
        level=logging.DEBUG,
        handlers=handlers,
    )


def readable_time(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def encode(msg):
    return json.dumps(msg).encode()


def decode(msg):
    return json.loads(msg.decode())


def change_status_task(chat_id, user_id, username, task_id, status):

    assert status in Status.ALL

    task = db.hget(f'/tasks/chat_id/{chat_id}', task_id)
    if task is None:
        return None

    task = decode(task)
    task['status'] = status
    task['modified'] = time.time()

    if status == Status.TODO:
        task['assignee_id'] = ''
        task['assignee'] = ''
    else:
        task['assignee_id'] = user_id
        task['assignee'] = username

    db.hset(f'/tasks/chat_id/{chat_id}', task_id, encode(task))
    return task


def get_formatted_username(username):
    if username[0] == '@':
        return username
    return f'@{username}'
