from shared.app import handler as dispatch


def handler(event, context):
    return dispatch(event, context)
