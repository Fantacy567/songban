"""Use real bounded HTTP reader with synthetic public article responses."""
import unittest
from unittest.mock import patch

import httpx
from app.contest_intel import IntelError
from app.materials_parse import parse_source


class MaterialLinkTests(unittest.TestCase):
    url = 'https://mp.weixin.qq.com/s/public-test-article'

    def parse(self, html):
        client_class = httpx.Client
        def reply(request):
            return httpx.Response(200, headers={'content-type': 'text/html; charset=utf-8'}, text=html)
        with patch('app.contest_intel.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), patch('app.materials_parse.httpx.Client', side_effect=lambda **kw: client_class(transport=httpx.MockTransport(reply), **kw)):
            return parse_source('url', self.url, self.url.encode())

    def test_multimegabyte_wechat_article_reads_only_body_and_keeps_original(self):
        html = '<html><body><div id="js_content"><p>比赛时间：11月7日。</p><div>提交要求：作品链接。</div></div><p>页面导航与广告</p><script>' + ('x' * 3_500_000) + '</script></body></html>'
        segments, warnings, original = self.parse(html)
        text = '\n'.join(s['text'] for s in segments)
        self.assertIn('比赛时间：11月7日。', text)
        self.assertIn('提交要求：作品链接。', text)
        self.assertNotIn('页面导航与广告', text)
        self.assertEqual(original, html.encode())

    def test_wechat_verification_is_not_accepted_as_article(self):
        with self.assertRaises(IntelError) as error:
            self.parse('<html><body>环境异常，请完成验证后继续访问</body></html>')
        self.assertEqual(error.exception.code, 'weixin_body_unavailable')
        self.assertIn('正文', error.exception.message)

    def test_web_limit_still_rejects_over_eight_megabytes(self):
        with self.assertRaises(IntelError) as error:
            self.parse('<html>' + ('x' * 8_000_001) + '</html>')
        self.assertEqual(error.exception.code, 'page_too_large')
