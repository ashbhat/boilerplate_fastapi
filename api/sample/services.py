from api.sample.schemas import EchoPayload

def echo(payload: EchoPayload):
    return payload.content