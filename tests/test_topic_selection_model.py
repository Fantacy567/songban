import json
import unittest
from unittest.mock import MagicMock, patch
import httpx
from app.planner import PlannerError
from app.topic_selection_model import request_ranking


class TopicModelTests(unittest.TestCase):
    config={'api_key':'synthetic-key','base_url':'https://api.deepseek.com','model_id':'synthetic-model'}

    def response(self,body,status=200):
        return httpx.Response(status,json=body)

    def invoke(self,response):
        client=MagicMock()
        if isinstance(response,Exception):client.post.side_effect=response
        else:client.post.return_value=response
        with patch('app.topic_selection_model.team_model_config',return_value=self.config),patch('app.topic_selection_model.httpx.Client') as factory:
            factory.return_value.__enter__.return_value=client
            result=request_ranking({'candidates':[],'coverage':{'truncated_turns':0}})
        return result,client,factory

    def test_request_metadata_and_no_redirect_or_environment_proxy(self):
        data={'summary':'评估结果','items':[]}
        r,client,factory=self.invoke(self.response({'model':'actual-reported-model','choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]}))
        self.assertEqual(r['requested_model'],'synthetic-model')
        self.assertEqual(r['actual_model'],'actual-reported-model')
        self.assertEqual(client.post.call_count,1)
        self.assertFalse(factory.call_args.kwargs['follow_redirects'])
        self.assertFalse(factory.call_args.kwargs['trust_env'])
        self.assertEqual(client.post.call_args.kwargs['json']['thinking'],{'type':'disabled'})

    def test_missing_configuration_never_calls_network(self):
        with patch('app.topic_selection_model.team_model_config',return_value={'api_key':''}),patch('app.topic_selection_model.httpx.Client') as client:
            with self.assertRaises(PlannerError) as error:request_ranking({})
            self.assertEqual(error.exception.code,'model_not_configured');client.assert_not_called()

    def test_invalid_or_incomplete_answer_not_accepted(self):
        for choice in ({'finish_reason':'length','message':{'content':'{"items":[]}'}},
                       {'message':{'content':'not-json'}},{'message':{'content':'[]'}},
                       {'message':{'content':None}}):
            with self.subTest(choice=choice),self.assertRaises(PlannerError) as error:
                self.invoke(self.response({'choices':[choice]}))
            self.assertEqual(error.exception.code,'model_invalid_output')

    def test_timeout_and_service_error_have_safe_messages(self):
        for response,expected in [(httpx.ReadTimeout('upstream sensitive details'),'model_timeout'),
                                   (httpx.ConnectError('upstream sensitive details'),'model_unavailable'),
                                   (self.response({'error':'upstream sensitive details'},401),'model_unavailable')]:
            with self.subTest(expected=expected),self.assertRaises(PlannerError) as error:self.invoke(response)
            self.assertEqual(error.exception.code,expected)
            self.assertNotIn('sensitive',error.exception.message)
