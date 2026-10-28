from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'agent'))
from racecoach_agent.runtime import Agent
from racecoach_agent.storage import AgentStore


def test_offline_upload_is_kept_and_retried_without_changing_chunk_id(tmp_path):
    class Launcher:
        def stop(self): pass
    class Hardware:
        def close(self): pass
    store = AgentStore(tmp_path / 'agent.sqlite3')
    agent = Agent('http://localhost', 'not-a-real-token', store, Launcher(), Hardware())
    agent.client.close()
    calls = []
    def handle(request):
        calls.append(request.content)
        return httpx.Response(503 if len(calls) == 1 else 200, json={'ok':True})
    agent.client = httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(handle))
    store.queue('/api/agent/attempts/one/telemetry', {'chunk_id':'stable-id','samples':[1]})
    with pytest.raises(httpx.HTTPStatusError):
        agent.flush()
    assert store.pending() is not None
    agent.flush()
    assert store.pending() is None and calls[0] == calls[1]
    agent.close()
    store.close()
