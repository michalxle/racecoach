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


def test_flush_drops_backwards_samples_and_skips_rejected_chunk(tmp_path):
    class Launcher:
        def stop(self): pass
    class Hardware:
        def close(self): pass
    store = AgentStore(tmp_path / 'agent.sqlite3')
    agent = Agent('http://localhost', 'not-a-real-token', store, Launcher(), Hardware())
    agent.client.close()
    sent = []
    def handle(request):
        sent.append((request.url.path, __import__('json').loads(request.content)))
        return httpx.Response(422 if 'bad' in request.content.decode() else 200, json={'ok': True})
    agent.client = httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(handle))
    samples = [{'seq': 1, 't': 164.1}, {'seq': 2, 't': 0.003}, {'seq': 3, 't': 164.14}]
    store.queue('/api/agent/attempts/one/telemetry', {'chunk_id': 'old', 'samples': samples})
    store.queue('/api/agent/attempts/one/telemetry', {'chunk_id': 'bad', 'samples': [{'seq': 4, 't': 165}]})
    store.queue('/api/agent/attempts/one/finish', {'status': 'completed'})
    agent.flush()
    assert [s['seq'] for s in sent[0][1]['samples']] == [1, 3]
    assert sent[-1][0].endswith('/finish') and store.pending() is None
    agent.close()
    store.close()
