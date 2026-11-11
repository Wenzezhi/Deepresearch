"""Exercise real SDK retry behavior with a local mock transport (no API charges)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from openai import APIStatusError, APITimeoutError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from services.llm import ResearchLLM

class RetryTests(unittest.TestCase):
    def check_attempts(self, failure, expected, stream=False):
        calls=[]
        def handle(request):
            calls.append(request)
            if failure=='timeout':raise httpx.ReadTimeout('test timeout',request=request)
            return httpx.Response(failure,json={'error':{'message':'test failure'}})
        transport=httpx.Client(transport=httpx.MockTransport(handle))
        with patch('hello_agents.core.llm.OpenAI') as factory:
            from openai import OpenAI
            factory.return_value=OpenAI(api_key='test',base_url='https://example.test/v1',http_client=transport)
            llm=ResearchLLM(model='test',provider='custom',api_key='test',base_url='https://example.test/v1')
        try:
            with patch('services.llm.time.sleep'):
                with self.assertRaises((APIStatusError,APITimeoutError)):
                    if stream:list(llm.stream_invoke([{'role':'user','content':'test'}]))
                    else:llm.invoke([{'role':'user','content':'test'}])
            self.assertEqual(len(calls),expected)
        finally:llm._client.close()
    def test_server_errors_stop_after_three_retries(self):self.check_attempts(503,4)
    def test_timeout_stops_after_three_retries(self):self.check_attempts('timeout',4)
    def test_stream_connection_has_same_limit(self):self.check_attempts(503,4,True)
    def test_auth_error_is_not_retried(self):self.check_attempts(401,1)
    def test_rate_limit_has_same_limit(self):self.check_attempts(429,4)

if __name__=='__main__':unittest.main()
