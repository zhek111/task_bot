import json
import os
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, \
    BotCommand
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, \
    CallbackContext
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
DATA_FILE = os.getenv("DATA_FILE")
MEDIA_DIR = os.getenv("MEDIA_DIR")

if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)


class TaskManager:

    @staticmethod
    def load_data():
        if not os.path.exists(DATA_FILE):
            return {}
        with open(DATA_FILE, 'r') as f:
            content = f.read()
            if not content:
                return {}
            return json.loads(content)

    @staticmethod
    def save_data(data):
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)

    @staticmethod
    def create_task(task_name, message):
        task_id = str(uuid4())
        task = {
            'id': task_id,
            'name': task_name,
            'content': message.text or '',
            'status': 'in_progress',
            'photo': None
        }

        if message.photo:
            photo = max(message.photo, key=lambda p: p.file_size)
            task['photo'] = os.path.join(MEDIA_DIR, f"{task_id}.jpg")
            photo.get_file().download(task['photo'])
            task['content'] = message.caption or ''

        data = TaskManager.load_data()
        data[task_id] = task
        TaskManager.save_data(data)
        return task

    @staticmethod
    def get_tasks(status):
        data = TaskManager.load_data()
        return [task for task in data.values() if task['status'] == status]

    @staticmethod
    def get_task(task_id):
        data = TaskManager.load_data()
        return data.get(task_id)

    @staticmethod
    def set_task_status(task_id, status):
        data = TaskManager.load_data()
        task = data.get(task_id)
        if task:
            task['status'] = status
            TaskManager.save_data(data)
        return task

    @staticmethod
    def delete_task(task_id):
        data = TaskManager.load_data()
        task = data.get(task_id)
        if task:
            if task['photo'] and os.path.exists(task['photo']):
                os.remove(task['photo'])
            del data[task_id]
            TaskManager.save_data(data)
        return task


def add_task(update: Update, context: CallbackContext):
    message = update.message.reply_to_message
    if not message:
        update.message.reply_text("Reply to a message with /add <task_name>")
        return

    task_name = ' '.join(context.args)
    if not task_name:
        update.message.reply_text("Provide a task name after /add")
        return

    task = TaskManager.create_task(task_name, message)
    update.message.reply_text(f"Task '{task['name']}' added")


def show_tasks(update: Update, context: CallbackContext, status):
    tasks = TaskManager.get_tasks(status)

    if not tasks:
        update.message.reply_text(f"No tasks with status '{status}'")
        return

    buttons = []
    for task in tasks:
        button = InlineKeyboardButton(
            task['name'],
            callback_data=f"show_task:{task['id']}:{update.message.message_id}"
        )
        buttons.append([button])

    back_button = InlineKeyboardButton(
        "Back",
        callback_data=f"back:{update.message.message_id}"
    )
    buttons.append([back_button])

    reply_markup = InlineKeyboardMarkup(buttons)
    update.message.reply_text(
        f"Tasks with status '{status}':", reply_markup=reply_markup
    )


def tasks_in_progress(update: Update, context: CallbackContext):
    show_tasks(update, context, 'in_progress')


def tasks_completed(update: Update, context: CallbackContext):
    show_tasks(update, context, 'completed')


def tasks_archived(update: Update, context: CallbackContext):
    show_tasks(update, context, 'archived')


def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Here are the available commands for the task bot:\n\n"
        "/add <task_name> - Reply to a message with this command to add a "
        "new task with the given name.\n"
        "/tasks - Show a list of tasks in progress.\n"
        "/completed - Show a list of completed tasks.\n"
        "/archive - Show a list of archived tasks.\n"
        "/help - Show this help message.\n\n"
        "Use inline buttons to interact with tasks and change their status "
        "or delete them."
    )
    update.message.reply_text(help_text)


def show_task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    _, task_id, command_message_id = query.data.split(':')

    task = TaskManager.get_task(task_id)
    if not task:
        query.answer("Task not found")
        return

    buttons = [
        [InlineKeyboardButton(
            "Mark as Completed",
            callback_data=
            f"set_status:completed:{task_id}:{command_message_id}")],
        [InlineKeyboardButton(
            "Mark as In Progress",
            callback_data=
            f"set_status:in_progress:{task_id}:{command_message_id}")],
        [InlineKeyboardButton(
            "Mark as Archived",
            callback_data=
            f"set_status:archived:{task_id}:{command_message_id}")],
        [InlineKeyboardButton(
            "Delete",
            callback_data=f"delete:{task_id}:{command_message_id}")],
        [InlineKeyboardButton(
            "Back",
            callback_data=f"back:{command_message_id}")],
    ]

    reply_markup = InlineKeyboardMarkup(buttons)
    query.delete_message()
    if task['photo']:
        with open(task['photo'], 'rb') as file:
            context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=file, caption=task['content'], reply_markup=reply_markup
            )
    else:
        context.bot.send_message(
            chat_id=query.message.chat_id,
            text=task['content'], reply_markup=reply_markup)

    context.bot.delete_message(
        chat_id=query.message.chat_id,
        message_id=command_message_id
    )


def set_status_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    _, status, task_id, command_message_id = query.data.split(':')

    task = TaskManager.set_task_status(task_id, status)
    if not task:
        query.answer("Task not found")
        return

    query.answer(f"Task status set to '{status}'")

    context.bot.delete_message(chat_id=query.message.chat_id,
                               message_id=query.message.message_id)


def delete_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    _, task_id, command_message_id = query.data.split(':')

    task = TaskManager.delete_task(task_id)
    if not task:
        query.answer("Task not found")
        return

    query.answer("Task deleted")

    context.bot.delete_message(chat_id=query.message.chat_id,
                               message_id=query.message.message_id)


def back_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    _, command_message_id = query.data.split(':')

    context.bot.delete_message(chat_id=query.message.chat_id,
                               message_id=query.message.message_id)


def set_bot_commands(bot):
    bot_commands = [
        BotCommand("add", "Add a new task (use in reply to a message)"),
        BotCommand("tasks", "Show a list of tasks in progress"),
        BotCommand("completed", "Show a list of completed tasks"),
        BotCommand("archive", "Show a list of archived tasks"),
        BotCommand("help", "Show help message with available commands"),
    ]
    bot.set_my_commands(bot_commands)


def main():
    updater = Updater(TOKEN, use_context=True)

    set_bot_commands(updater.bot)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("add", add_task))
    dp.add_handler(CommandHandler("tasks", tasks_in_progress))
    dp.add_handler(CommandHandler("completed", tasks_completed))
    dp.add_handler(CommandHandler("archive", tasks_archived))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(
        CallbackQueryHandler(show_task_callback, pattern="^show_task:"))
    dp.add_handler(
        CallbackQueryHandler(set_status_callback, pattern="^set_status:"))
    dp.add_handler(CallbackQueryHandler(delete_callback, pattern="^delete:"))
    dp.add_handler(CallbackQueryHandler(back_callback, pattern="^back:"))
    dp.add_handler(CallbackQueryHandler(back_callback, pattern="^back_task:"))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
