"""运行：python3 -m unittest discover -s tools/eval_viewer -p 'test_*.py'"""
import json
import io
from pathlib import Path
import tempfile
import unittest
from serve import build_index, normalize, make_handler


class ViewerTest(unittest.TestCase):
    def test_python_repr_and_nested_json(self):
        self.assertEqual(normalize("{'items_json': '[{\"agent_type\": \"search_agent\"}]'}"),
                         {'items_json': [{'agent_type': 'search_agent'}]})
        self.assertEqual(normalize('[not json'), '[not json')
        self.assertEqual(normalize('__import__("os").getcwd()'), '__import__("os").getcwd()')

    def test_same_question_cases_and_missing_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for variant in ('single', 'multi'):
                p = root / variant / 'q1'
                p.mkdir(parents=True)
                (p/'eval_result.json').write_text(json.dumps({'id': 'q1', 'question': '同一题',
                    'benchmark': 'test', 'metrics': {'f1_by_item': .5, 'large_details': 'omit'}}))
            conv = root/'multi/q1/session/conversations'
            conv.mkdir(parents=True)
            (conv/'orchestrator.json').write_text('{}')
            (root/'multi/q1/session/trajectory.jsonl').write_text('')
            records = build_index(root)
            self.assertEqual(len(records), 2)
            self.assertEqual({r['id'] for r in records}, {'q1'})
            self.assertEqual(sum(r['trajectory'] for r in records), 1)
            self.assertEqual(sum(len(r['agents']) for r in records), 1)
            self.assertTrue(all(r['metrics'] == {'f1_by_item': .5} for r in records))

    def test_session_without_eval_is_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = root/'ablation/with_tool_result_compression/run/ws_en_005/session'
            conv = session/'conversations'
            conv.mkdir(parents=True)
            (conv/'orchestrator.json').write_text(json.dumps({'task': '原始问题', 'messages': []}))
            (session/'trajectory.jsonl').write_text(json.dumps({'type': 'task_start', 'query': '处理后的问题'})+'\n')
            records = build_index(root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['id'], 'ws_en_005')
            self.assertEqual(records[0]['benchmark'], 'widesearch')
            self.assertEqual(records[0]['status'], '未出评测结果')
            self.assertEqual(records[0]['question'], '原始问题')
            self.assertEqual(records[0]['agents'], ['orchestrator'])

    def test_file_access_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'eval_result.json').write_text('{"id": "q1"}')
            (root/'private.txt').write_text('private')
            handler_type = make_handler(root)
            for url, expected in [('/api/file?path=eval_result.json', 200),
                                  ('/api/file?path=private.txt', 403),
                                  ('/api/file?path=../outside.json', 404)]:
                handler = object.__new__(handler_type)
                handler.path = url
                handler.wfile = io.BytesIO()
                codes = []
                handler.send_response = codes.append
                handler.send_error = lambda code, *args: codes.append(code)
                handler.send_header = lambda *args: None
                handler.end_headers = lambda: None
                handler.do_GET()
                self.assertEqual(codes, [expected])


if __name__ == '__main__':
    unittest.main()
