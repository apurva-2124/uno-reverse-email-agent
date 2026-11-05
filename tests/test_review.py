import http.client
import json
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit


class ReviewHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = [sys.executable, '-m', 'uno_reverse', '--state', cls.temp.name]
        subprocess.run(cls.base + ['demo'], check=True, capture_output=True)
        subprocess.run(cls.base + ['scan', '--yes'], check=True, capture_output=True)
        cls.process = subprocess.Popen(cls.base + ['review', '--no-browser'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = cls.process.stdout.readline()
        if ' — ' not in line:
            _, error = cls.process.communicate(timeout=5)
            raise RuntimeError('Review server failed to start: ' + error)
        cls.url = urlsplit(line.split(' — ', 1)[1].strip())
        cls.host = cls.url.netloc
        cls.token = cls.url.fragment

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.temp.cleanup()

    def request(self, path, method='GET', body=None, token=True, origin=None, host=None, content_type='application/json'):
        connection = http.client.HTTPConnection(self.host, timeout=5)
        headers = {'Host': host or self.host}
        if token:
            headers['Authorization'] = 'Bearer ' + self.token
        if origin is not None:
            headers['Origin'] = origin
        raw = json.dumps(body) if body is not None else None
        if raw:
            headers['Content-Type'] = content_type
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        data = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, data, response_headers

    def test_static_page_never_contains_session_token_or_source_body(self):
        status, body, headers = self.request('/', token=False)
        self.assertEqual(status, 200)
        self.assertNotIn(self.token.encode(), body)
        self.assertNotIn(b'123456', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        for path in ['/app.js','/style.css']:
            self.assertEqual(self.request(path, token=False)[0], 200)

    def test_state_requires_token_and_rejects_host_or_origin_attack(self):
        self.assertEqual(self.request('/api/state', token=False)[0], 401)
        self.assertEqual(self.request('/api/state', host='evil.example')[0], 403)
        self.assertEqual(self.request('/api/state', origin='https://evil.example')[0], 403)
        status, body, _ = self.request('/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['candidates']), 3)

    def test_mutations_require_origin_token_and_json(self):
        self.assertEqual(self.request('/api/pause','POST',{},origin=None)[0], 403)
        self.assertEqual(self.request('/api/pause','POST',{},origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('/api/pause','POST',{},token=False,origin='http://'+self.host)[0], 401)
        self.assertEqual(self.request('/api/pause','POST',{},origin='http://'+self.host,content_type='text/plain')[0], 415)

    def test_browser_approval_flow_uses_exact_hash(self):
        state = json.loads(self.request('/api/state')[1])
        c = next(c for c in state['candidates'] if c['source_id'] == 'sales-1')
        origin='http://'+self.host
        self.assertEqual(self.request('/api/approve','POST',{'id':c['id'],'hash':'stale'},origin=origin)[0], 400)
        self.assertEqual(self.request('/api/approve','POST',{'id':c['id'],'hash':c['hash']},origin=origin)[0], 200)
        status, body, _=self.request('/api/send','POST',{'id':c['id']},origin=origin)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['result'],'accepted_by_gmail')

    def test_bad_json_shape_is_rejected(self):
        self.assertEqual(self.request('/api/pause','POST',[],origin='http://'+self.host)[0], 400)
