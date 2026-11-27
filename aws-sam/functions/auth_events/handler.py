from shared.app import login_event_handler


def handler(event, context):
    return login_event_handler(event, context)
