import logging
import time
from tempfile import TemporaryFile

from singleton import bot, db
from telebot import types
from utils import Status, change_status_task, decode, encode, readable_time
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
    response, keyboard = get_my_tasks(message, status, offset)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


def get_my_tasks(message, status, offset):
    last_task_id = db.get(f'/tasks/chat_id/{message.chat.id}/last_task_id')
    # task_id = int(last_task_id) - offset
    task_id = int(last_task_id)
    offset_for_calculating = offset
    tasks = {}

    print(
        f'get_my_tasks -> offset = {offset}, last_task_id = {last_task_id},'
        f'status = {status}, task_id = {task_id}')

    is_next_btn_enabled = False

    while task_id > 0 and len(tasks) < LIMIT + 1:
        task, *_ = db.hmget(f'/tasks/chat_id/{message.chat.id}', task_id)
        task_id -= 1
        if not task:
            continue
        task = decode(task)
        if status in Status.ALL and task['status'].upper() != status:
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
            [f'/{task_id:<4} {task["status"]:<4} {task["title"]} '
             f'{task["assignee"]}'
             for task_id, task in tasks.items()]
        )
    else:
        response = f"No tasks for such offset {offset} and status {status}"

    keyboard = types.InlineKeyboardMarkup(row_width=3)
    btns = []
    # first if
    if int(last_task_id) - offset < int(last_task_id):
        print(f'first if: last_task_id = {last_task_id}; offset = {offset}')
        btns.append(types.InlineKeyboardButton(
            text='Prev', callback_data=f"my_tasks:{status}:{offset - 10}"))
    # second if
    # wrong condition
    # if int(last_task_id) - offset > 10:
    if is_next_btn_enabled:
        print(f'second if: last_task_id = {last_task_id}; offset = {offset}')
        btns.append(types.InlineKeyboardButton(
            text='Next', callback_data=f"my_tasks:{status}:{offset + 10}"))

    if status.upper() == Status.DO:
        btns.append(types.InlineKeyboardButton(
            text='Done', callback_data=f"my_tasks:{Status.DONE}:0"))
    elif status.upper() == Status.DONE:
        btns.append(types.InlineKeyboardButton(
            text='Do', callback_data=f"my_tasks:{Status.DO}:0"))

    keyboard.add(*btns)
    return response, keyboard


@bot.message_handler(commands=['do'])
@validate(task_id=arg(int, required=True))
def do(message, task_id):
    task = change_status_task(message, task_id, status=Status.DO)
    if task:
        return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')


@bot.message_handler(commands=['todo'])
@validate(task_id=arg(int, required=True))
def todo(message, task_id):
    task = change_status_task(message, task_id, status=Status.TODO)
    if task:
        return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')


@bot.message_handler(commands=['done'])
@validate(task_id=arg(int, required=True))
def done(message, task_id):
    task = change_status_task(message, task_id, status=Status.DONE)
    if task:
        return bot.reply_to(message, f'''Title: {task["title"]}
Status: {task["status"]}
Assignee: {task["assignee"]}
Description:
{task["description"]}''')


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
    response, keyboard = get_tasks(message, status, offset)
    return bot.send_message(
        message.chat.id,
        response,
        reply_markup=keyboard
    )


def get_tasks(message, status, offset):
    last_task_id = db.get(
        f'/tasks/chat_id/{message.chat.id}/last_task_id')
    task_id = int(last_task_id) - offset
    tasks = {}

    while task_id > 0 and len(tasks) < LIMIT:
        task, *_ = db.hmget(f'/tasks/chat_id/{message.chat.id}', task_id)
        task_id -= 1
        if not task:
            continue
        task = decode(task)
        if status in Status.ALL and task['status'].upper() != status:
            continue
        tasks[task_id + 1] = task

    if tasks:
        response = '\n'.join(
            [f'/{task_id:<4} {task["status"]:<4} {task["title"]} '
             f'{task["assignee"]}'
             for task_id, task in tasks.items()]
        )
    else:
        response = f"No tasks for such offset {offset} and status {status}"

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    if int(last_task_id) - offset < int(last_task_id):
        btns.append(types.InlineKeyboardButton(
            text='Prev', callback_data=f"tasks:{status}:{offset - 10}"))
    if int(last_task_id) - offset > 10:
        btns.append(types.InlineKeyboardButton(
            text='Next', callback_data=f"tasks:{status}:{offset + 10}"))
    keyboard.add(*btns)
    return response, keyboard


@bot.callback_query_handler(func=lambda call: call.message)
def callback_inline(call):
    cmd, status, offset = call.data.split(':')
    if cmd == 'tasks':
        response, keyboard = get_tasks(call.message, status, int(offset))
        return bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response,
            reply_markup=keyboard,
        )
    elif cmd == 'my_tasks':
        response, keyboard = get_my_tasks(call.message, status, int(offset))
        return bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response,
            reply_markup=keyboard,
        )

    # If message from inline mode
    # elif call.inline_message_id:
    #     if call.data == "category":
    #         bot.edit_message_text(
    #             inline_message_id=call.inline_message_id,
    #             text=f"Choosed category2 {call.message}"
    #         )


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

    print(f'task = {task}')
    task = decode(task)
    task['title'] = title
    task['description'] = description
    task['modified'] = timestamp

    db.hset(f'/tasks/chat_id/{message.chat.id}', task_id, encode(task))
    return bot.reply_to(message, f'Modified task with id /{task_id}')


@bot.message_handler(regexp=r"^/[0-9]*$")
def get_task(message):
    try:
        task_id = int(message.text.replace('/', '', 1).strip().split()[0])
    except Exception:
        bot.reply_to(message, "Wrong syntax!")

    task = db.hget(f'/tasks/chat_id/{message.chat.id}', task_id)

    if task is None:
        return bot.reply_to(message, 'No task with such id')

    task = decode(task)
    return bot.reply_to(message, f'''Task id: {task_id}
Title: {task["title"]}
Status: {task["status"]}
Created: {readable_time(task["created"])}
Modified: {readable_time(task["modified"])}
Assignee: {task["assignee"]}
Assignee id: {task["assignee_id"]}
Description:
{task["description"]}''')


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
