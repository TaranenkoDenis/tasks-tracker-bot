import logging
import time
from tempfile import TemporaryFile

from singleton import bot, db
from telebot import types
from utils import (Status, change_status_task, decode, encode, readable_time,
                   get_formatted_username)
from validator import arg, status_enum, validate

log = logging.getLogger(__name__)
LIMIT = 10
HELP = """This is simple task manager
/start - shows help message
/help - shows help message
/new title\n
    description of task
/tasks (default show all tasks)
/tasks todo 10
/tasks done 10
/tasks all 5
/export - exports to csv file
/task [task_id] - print detailed info about task by id
/do - mark task status as DO
/done - mark task status as DONE
/todo - mark task status as TODO
"""


@bot.message_handler(commands=['my'])
@validate(status=arg(status_enum, Status.DO), offset=arg(int, 0))
def my_tasks(message, status, offset):
    """
    By default prints tasks with status do.
    """

    response, keyboard = get_tasks(message.chat.id, status,
                                   offset, message.from_user.id)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


def get_tasks(chat_id, status, offset=0, user_id=None):
    last_task_id = db.get(f'/tasks/chat_id/{chat_id}/last_task_id')
    task_id = int(last_task_id) if last_task_id else 0

    user_id = None if (
        user_id == 'None' or user_id is None) else int(user_id)

    offset = int(offset)
    offset_for_calculating = offset
    tasks = {}

    is_next_btn_enabled = False

    while task_id > 0 and len(tasks) < LIMIT + 1:
        task, *_ = db.hmget(f'/tasks/chat_id/{chat_id}', task_id)
        task_id -= 1

        if not task:
            continue

        task = decode(task)
        task['assignee_id'] = str(task['assignee_id'])
        user_id = str(user_id) if user_id is not None else None

        if task['status'].upper() != status or (
                user_id is not None and
                task['assignee_id'] != user_id):
            continue

        if offset_for_calculating > 0:
            offset_for_calculating -= 1
            continue

        if len(tasks) < LIMIT:
            tasks[task_id + 1] = task
        else:
            is_next_btn_enabled = True
            break

    if tasks:
        response = '\n'.join(
            [f'/{task_id:<4} /{task["status"].lower():<4} {task["title"]} '
             f'{task["assignee"]}'
             for task_id, task in tasks.items()]
        )
    else:
        response = f"No tasks with {status} status"

    keyboard = types.InlineKeyboardMarkup(row_width=3)
    btns = []
    if int(last_task_id) - offset < int(last_task_id):
        btns.append(types.InlineKeyboardButton(
            text='Prev', callback_data=f"tasks:{status}:{offset - 10}:"
                                       f"{user_id}"))
    if is_next_btn_enabled:
        btns.append(types.InlineKeyboardButton(
            text='Next', callback_data=f"tasks:{status}:{offset + 10}:"
                                       f"{user_id}"))

    if user_id:
        if status.upper() == Status.DO:
            btns.append(types.InlineKeyboardButton(
                text='Show Done',
                callback_data=f"tasks:{Status.DONE}:0:{user_id}")
            )
        elif status.upper() == Status.DONE:
            btns.append(types.InlineKeyboardButton(
                text='Show Do',
                callback_data=f"tasks:{Status.DO}:0:{user_id}")
            )

    keyboard.add(*btns)
    return response, keyboard


@bot.message_handler(commands=['do'])
@validate(task_id=arg(int, 0))
def do(message, task_id):
    if task_id:
        task = change_status_task(message.chat.id,
                                  message.from_user.id,
                                  get_formatted_username(
                                      message.from_user.username),
                                  task_id, status=Status.DO)
        if task:
            return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')
        return

    response, keyboard = get_tasks(message.chat.id, Status.DO, 0)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['todo'])
@validate(task_id=arg(int, 0))
def todo(message, task_id):
    if task_id:
        task = change_status_task(message.chat.id,
                                  message.from_user.id,
                                  get_formatted_username(
                                      message.from_user.username),
                                  task_id, status=Status.TODO)
        if task:
            return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')
        return

    response, keyboard = get_tasks(message.chat.id, Status.TODO, 0)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['done'])
@validate(task_id=arg(int, 0))
def done(message, task_id):
    if task_id:
        task = change_status_task(message.chat.id,
                                  message.from_user.id,
                                  get_formatted_username(
                                      message.from_user.username),
                                  task_id, status=Status.DONE)
        if task:
            return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')
        return

    response, keyboard = get_tasks(message.chat.id, Status.DONE, 0)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['new'])
def new(message):
    msg = message.text.replace('/new', '', 1)
    args = msg.split('\n', 1)
    if len(args) == 2:
        title, description = msg.split('\n', 1)
    else:
        title, description = msg, ''

    if len(title) > 256:
        return bot.reply_to(message, f'Title should be less than 256 chars')
    if len(description) > 2048:
        return bot.reply_to(
            message, f'Description should be less than 2048 chars'
        )

    timestamp = time.time()

    task_id = db.incr(f'/tasks/chat_id/{message.chat.id}/last_task_id')

    task = {
        'title': title.strip().capitalize(),
        'description': description,
        'created': timestamp,
        'modified': timestamp,
        'status': Status.TODO,
        'assignee': '',  # task will be assigned, when someone take it
        'assignee_id': '',
    }

    db.hset(f'/tasks/chat_id/{message.chat.id}', task_id, encode(task))

    return bot.reply_to(message, f'Created new task with id /{task_id}')


@bot.message_handler(commands=['tasks'])  # /tasks [opt: task_id]
@validate(status=arg(status_enum, Status.TODO), offset=arg(int, 0))
def tasks(message, status, offset):
    response, keyboard = get_tasks(message.chat.id, status, offset)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


@bot.message_handler(commands=['update'])
def update(message):
    msg = message.text.replace('/update', '', 1)
    args = msg.split('\n', 2)

    if len(args) == 3:
        task_id, title, description = msg.split('\n', 2)
    else:
        task_id, title, description = args[0], args[1], ''

    timestamp = time.time()
    task_id = int(task_id)

    task = db.hget(f'/tasks/chat_id/{message.chat.id}', task_id)

    task = decode(task)
    task['title'] = title
    task['description'] = description
    task['modified'] = timestamp

    db.hset(f'/tasks/chat_id/{message.chat.id}', task_id, encode(task))
    return bot.reply_to(message, f'Modified task with id /{task_id}')


@bot.message_handler(regexp=r"^/[0-9]*$")
def task(message):

    try:
        task_id = int(message.text.replace('/', '', 1).strip().split()[0])
    except Exception:
        bot.reply_to(message, "Wrong syntax!")

    response, keyboard = get_task(message.chat.id, message.from_user.id,
                                  message.from_user.username, task_id)
    return bot.send_message(
        message.chat.id,
        response,
        reply_to_message_id=message.message_id,
        reply_markup=keyboard
    )


def get_task(chat_id, user_id, username, task_id):
    task = db.hget(f'/tasks/chat_id/{chat_id}', task_id)

    if task is None:
        return 'No task with such id', None

    task = decode(task)

    response = f'''Task id: {task_id}
Title: {task["title"]}
Status: {task["status"]}
Created: {readable_time(task["created"])}
Modified: {readable_time(task["modified"])}
Assignee: {task["assignee"]}
Assignee id: {task["assignee_id"]}
Description:
{task["description"]}'''

    return response, get_keyboard_change_status(user_id, username, task_id)


def get_keyboard_change_status(user_id, username, task_id):
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    btns = [
        types.InlineKeyboardButton(
            text='TODO',
            # cmd, status, user_id, username, task_id=data
            callback_data=f"set_status_task:{Status.TODO}:{user_id}:"
                          f"{username}:{task_id}"
        ),
        types.InlineKeyboardButton(
            text='DO',
            callback_data=f"set_status_task:{Status.DO}:{user_id}:"
                          f"{username}:{task_id}"
        ),
        types.InlineKeyboardButton(
            text='DONE',
            callback_data=f"set_status_task:{Status.DONE}:{user_id}:"
                          f"{username}:{task_id}"
        )
    ]

    keyboard.add(*btns)
    return keyboard


@bot.callback_query_handler(func=lambda call: call.message)
def callback_inline(call):
    data = call.data.split(':')
    if data[0] == 'tasks':
        cmd, status, offset, user_id = data

        response, keyboard = get_tasks(call.message.chat.id, status,
                                       offset, user_id)
        return bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response,
            reply_markup=keyboard,
        )
    elif data[0] == 'set_status_task':
        cmd, status, user_id, username, task_id = data

        task = change_status_task(call.message.chat.id,
                                  user_id, get_formatted_username(username),
                                  task_id, status)

        if task is None:
            response = 'No task with such id'
        else:
            response = f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}'''

        return bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response,
            reply_markup=get_keyboard_change_status(user_id, username, task_id)
        )

    # If message from inline mode
    # elif call.inline_message_id:
    #     if call.data == "category":
    #         bot.edit_message_text(
    #             inline_message_id=call.inline_message_id,
    #             text=f"Choosed category2 {call.message}"
    #         )


@bot.message_handler(commands=['export'])
def export(message):
    with TemporaryFile() as f:
        last_task_id = db.get(
            f'/tasks/chat_id/{message.chat.id}/last_task_id')

        if not last_task_id:
            return bot.reply_to(message, "There are no records.")

        task, *_ = db.hmget(f'/tasks/chat_id/{message.chat.id}', last_task_id)

        fieldnames = sorted(['task_id'] + list(decode(task).keys()))
        f.write((','.join(fieldnames)).encode())

        for t in db.hscan_iter(f'/tasks/chat_id/{message.chat.id}'):
            f.write(b'\n')
            task = decode(t[1])
            task['task_id'] = t[0].decode()
            row = ','.join([str(task[field]) for field in fieldnames])
            f.write(row.encode('utf-8'))

        f.seek(0)

        bot.send_document(message.chat.id, f, caption='report.csv')


@bot.message_handler(commands=['help'])
def help_msg(message):
    return bot.reply_to(message, HELP)


@bot.message_handler(commands=['start'])
def start(message):
    return bot.reply_to(message, 'Here will be start message')
