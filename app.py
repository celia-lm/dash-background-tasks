import dash_ag_grid as dag
import datetime
import dash
from dash import Dash, Input, Output, State, html, dcc, callback, ctx
# my tasks file
import tasks
from tasks import background_callback_manager, celery_app, mytask_unwrapped, retrieve_data_from_db

app = Dash(__name__, background_callback_manager=background_callback_manager)
server = app.server

# this is just a shortcut for basic styling without ddk
def control_item(component):
    return html.Div(component + [html.Br()], style={"padding":"5px"})

app.layout = html.Div(
    [   
        html.H3("App status:"), 
        # these two html.Span could be ddk.Notification
        html.Span(id="app-status", children="No updates have been triggered by the user yet"), html.Br(),
        html.Span(id="last-update"), html.Br(),
        dcc.Store(id="task-id-store"),
        ## inputs for celery task and bg callback
        html.H3("Please specify:"), 
        control_item([
            html.Span("The number of new records you want to add to the dataframe:"),
            dcc.Input(id="new_values_n", type="number", min=0, value=1),
        ]),
        control_item([
            html.Span("How long (number of seconds) the task will take to complete:"),
            dcc.Input(id="wait", type="number", min=0, value=10), 
        ]),
        ## buttons
        control_item([
            html.Span("How you want the task to be executed:"), html.Br(),
            html.Button(id="button_bg_callback", children="Update DB with background callback"),
            html.Button(id="button_celery", children="Update DB with regular callback + celery task")
        ]),
        ## table and (invisible) interval to update it without refreshing the page
        html.H3("Results:"),
        dcc.Interval(id="interval", interval=1*1000, disabled=True), # 1 second (1000 miliseconds)
        dag.AgGrid(
            id="table",
            rowData=[],
            columnDefs=[{"field":c} for c in ["creation_time", "col_numeric", "col_category"]]
        )
    ],
    style={"padding":'10px'}
)

# this callback sends the task to a background queue (which is also celery) but it won't finish until the task has been COMPLETED
# with a background callback we'll be notified as soon as the process has finished
@callback(
    Output("last-update", "children"),
    Input("button_bg_callback", "n_clicks"),
    State("new_values_n", "value"),
    State("wait", "value"),
    background=True,
    prevent_initial_call=True
)
def update_data_bg(_, new_values_n, wait_seconds):
    # I use dash.set_props for performance and simplicity
    # it helps me avoid specifying "app-status" as an additional Output of this callback
    # and the update happens clientside (which is faster)
    dash.set_props("app-status", {"children":"A background callback update is being executed"})
    start = datetime.datetime.now().strftime("%H:%M:%S")
    mytask_unwrapped(N=new_values_n, sleep_time=wait_seconds)
    finish = datetime.datetime.now().strftime("%H:%M:%S")
    dash.set_props("app-status", {"children":f"Background callback for data update started at {start} and finished at {finish}"})
    return f"Last data update was at {finish}"

# this callback sends the task to celery 
# and (THIS IS OPTIONAL) saves the task id to the dcc.Store so that we can check when it has finished
# because this callback will finish as soon as the task has been SENT, not completed
@callback(
    Output("task-id-store", "data"),
    Input("button_celery", "n_clicks"),
    State("new_values_n", "value"),
    State("wait", "value"),
    prevent_initial_call=True
)
def update_data_celery(_, new_values_n, wait_seconds):
    start = datetime.datetime.now().strftime("%H:%M:%S")
    task_id = celery_app.send_task('add_new_values',  kwargs = {"N":new_values_n, "sleep_time":wait_seconds})
    dash.set_props("app-status", {"children":f"Task has been sent to celery at {start} and it will take {wait_seconds} seconds."})
    return str(task_id)

# we won't be notified automatically when a celery task has finished; we will need to use a periodic check
# we use interval.disabled as output so that the interval is only counting/running when we know a celery task is being executed
# this will only applied to the celery task triggered by the user
# if we want to do something similar for the scheduled tasks, the interval would need to run permanently 
# and we would need additional code (to save the task_id of the scheduled task to the redis db with hset and hget) 
@callback(
    Output("interval", "disabled"),
    Input("task-id-store", "data"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True
)
def check_task_status(task_id, _intervals):
    if ctx.triggered_id == "task-id-store":
        return False # start interval
    elif ctx.triggered_id == "interval" and task_id:
        res = celery_app.AsyncResult(task_id)
        if res.ready():
            now = datetime.datetime.now().strftime("%H:%M:%S")
            dash.set_props("last-update", {"children":f"Last data update was at {now}"})
            return True # stop interval

    return dash.no_update

# update table data when the last-update information html.Span is updated
# last-update will be updated both if the source of the update is the bg callback or the celery task
@callback(
    Output("table", "rowData"),
    Input("last-update", "children"),
    prevent_initial_call=False
)
def update_table(_last_update):
    updated_data = retrieve_data_from_db()
    if updated_data:
        return updated_data
    else :
        return dash.no_update

if __name__ == "__main__":
    app.run(debug=True)
