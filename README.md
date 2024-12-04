This app demoes how to **execute background tasks** in a Dash App in multiple ways:
1. As a **scheduled task**
2. As a **background callback**
3. As a **celery task inside a regular callback**

These background tasks generate random data (based in user inputs) that is appended to the existing one in a Redis database and saved there. That data is then retrieved from a regular dash callback to populate a Dash Ag Grid:
<img width="681" alt="Screenshot 2024-12-04 at 16 53 30" src="https://github.com/user-attachments/assets/1b1d330b-76c1-4b7c-922d-a90524b86e6a">

This app has been designed to be deployed to **Dash Enterprise 5** and assumes that you have **linked a Redis database** to your app, whose url is available as the `REDIS_URL` environment variable.

The library versions specified in **requirements.txt** are the most up-to-date for Python 3.9 at the time of the creation of this code (December 4 2024); they can probably be updated to later versions if you are checking this app at a later date.

All the code is commented but in the following lines there's an explanation of the logic and the decisions that have been taken, organized by the file name.

**tasks.py**
- We only create [one celery_app](https://github.com/celia-lm/dash-background-tasks/blob/main/tasks.py#L11-L13) which we then use to create the `background_callback_manager` and to define celery tasks with `@celery_app.task(name=task_name)`.
- We create the `celery_app`, the `background_callback_manager` and the tasks in this file so that we can import them into `app.py` and **avoid circular dependencies**.
- We define the [mytask_unwrapped](https://github.com/celia-lm/dash-background-tasks/blob/main/tasks.py#L31-L51) function as a regular function instead of a celery task directly because that way we can use it in both ways: calling it as a regular function (inside a background callback) or as a celery task (inside `mytask_wrapped` function, which is decorated with `@celery_app.task("add_new_values)`)
- Instead of using the traditional `@celery_app.on_after_configure.connect` decorator to define the **scheduled tasks**, we use the [`celery_app.conf.beat_schedule` dictionary](https://github.com/celia-lm/dash-background-tasks/blob/main/tasks.py#L66-L71) because Dash doesn't seem to register correctly the tasks otherwise.

**app.py**
- We import the relevant functions and objects from `tasks`, like `background_callback_manager`
- The layout includes some components that are merely informative, like `app-status`.
- The "Please specify" section allows end users to modify the arguments for the background task and how they want to execute it.
- In multiple callbacks  [use `dash.set_props` is used for performance and simplicity](https://dash.plotly.com/advanced-callbacks#setting-properties-directly); it helps me avoid specifying "app-status" as an additional Output of this callback and the update happens clientside (which is faster).
- For the **scheduled task**, there's no relevant code in this file. To see data updates triggered by the scheduled task, we'll need to refresh the page. It's possible to implement code that updates the table automatically when the scheduled task is finished but it would be complex - it would require a dcc.Interval component running permanently and storing the scheduled task id in the Redis DB.
- Inside the **background callback**, [we call the raw `mytask_unwrapped` function](https://github.com/celia-lm/dash-background-tasks/blob/main/app.py#L66). Background callbacks run in a background queue (which is also celery) but they won't finish (i.e. the Outputs won't be updated) until the task has been COMPLETED. ALL of the code of that callback will be run in the background, not only `mytask_unwrapped`. **Background callbacks are the easiest option if we want to send a notification as soon as the process has finished**.
- To send the **Celery task from inside a regular callback** we use [`celery_app.send_task('add_new_values',  ...)`] (https://github.com/celia-lm/dash-background-tasks/blob/main/app.py#L83C15-L83C57).
  - It is **important** that the task name we specify in this command is the same that we have specified in `@celery_app.task(name=task_name)`in the tasks.py file. Otherwise, we will get a `Received unregistered task of type WRONG_NAME` error message in the celery worker-default logs.
  - The result of the `send_task` method is the **task id**. We assign it to a Python object and then save it in a dcc.Store so that we can use that information to check if the callback has finished with the [`check_task_status` callback](https://github.com/celia-lm/dash-background-tasks/blob/main/app.py#L87-L108).

**Procfile**
- The first line is the common `gunicorn` command to run a Dash app in deployment.
- The second line, worker-default, runs the `celery_app` where **all the background tasks** will be executed. **What we do in the app code is simply specify different ways to send the tasks to this queue**. `app:celery_app` tells Dash to look for the `celery_app` object in the `app.py` file. It's available in `app.py` because we have imported it, otherwise Dash wouldn't be able to find it. We specify it there and not in `tasks.py` because we need the background callback to be registered, and the background callback is only defined in app.py
- The third line, worker-beat, sends the scheduled task to worker-default based on `celery_app.conf.beat_schedule`.
