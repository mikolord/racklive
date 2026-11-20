"""Frank desktop protocol and tool loop; no real screen or input."""
import json, tempfile, types, unittest
from unittest.mock import patch
from rackd import assistant, frankdesktop

class InputTests(unittest.TestCase):
 def test_pointer_drag_keys_and_unicode(self):
  s=frankdesktop.Session(None,None);s.w,s.h=2000,1000;s.dimensions();messages=[];s.send=messages.append
  with patch('rackd.frankdesktop.time.sleep'):
   s.action({'op':'drag','x':100,'y':100,'to_x':300,'to_y':200})
  self.assertEqual(messages[1][1],1);self.assertEqual(messages[-1][1],0)
  messages.clear();s.action({'op':'key','key':'win+r'});self.assertEqual([x[1] for x in messages],[1,1,0,0])
  messages.clear();s.action({'op':'type','text':'Я'});self.assertEqual(int.from_bytes(messages[0][-4:],'big'),0x0100042f)
  with self.assertRaises(Exception):s.action({'op':'click','x':-1,'y':1})
 def test_png(self):
  s=frankdesktop.Session(None,None);s.w=s.h=2;s.dimensions();png=s.png(bytes([0,0,255,0]*4));self.assertTrue(png.startswith(b'\x89PNG'))

class LoopTests(unittest.TestCase):
 def run_loop(self,proto='openai',mode=True,quote='Открой рабочий стол'):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  store=types.SimpleNamespace(dir=tmp.name,add_event=lambda *a:None)
  app=types.SimpleNamespace(store=store,desktop=object(),demo=False)
  cfg={'proto':proto,'base':'https://api.deepseek.com' if proto=='openai' else 'https://api.anthropic.test','model':'deepseek-v4-pro' if proto=='openai' else 'test','key':'x','noKey':False,'actions':True,'admin':True,'agent':True,'full':mode,'agentMode':'full','browser':False,'effort':'','window':10000}
  calls=[];counter=[0];img=b'\x89PNG\r\n\x1a\n' + b'x'*1100
  def post(c,url,body,headers):
   calls.append(body.copy());counter[0]+=1
   args={'device':'PC','op':'shot','request':quote}
   if proto=='openai':
    if counter[0]==1:return {'choices':[{'message':{'tool_calls':[{'id':'1','function':{'name':'windows_desktop','arguments':json.dumps(args)}}]}}]}
    return {'choices':[{'message':{'content':'Готово'}}]}
   if counter[0]==1:return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':'1','name':'windows_desktop','input':args}]}
   return {'stop_reason':'end_turn','content':[{'type':'text','text':'Готово'}]}
  with patch.object(assistant,'resolved',lambda c:c),patch.object(assistant,'build_system',lambda *a:'system'),patch.object(assistant,'fixed_tokens',lambda *a:(1,1)),patch.object(assistant,'_find_device',lambda *a:{'id':'pc','name':'PC','driver':'windows'}),patch.object(assistant.frankdesktop,'run',return_value=(img,1280,720)) as run,patch.object(assistant,'_post',side_effect=post):
   result=assistant.ask(app,cfg,[{'role':'user','text':'Открой рабочий стол'}])
  return calls,result,run.call_count
 def test_openai_image_and_vision_model(self):
  calls,result,count=self.run_loop();self.assertEqual(count,1);self.assertEqual(calls[1]['model'],'deepseek-flash');self.assertEqual(calls[1]['messages'][-1]['content'][-1]['type'],'image_url');self.assertEqual(len(result['shots']),1)
 def test_anthropic_image_tool_result(self):
  calls,result,count=self.run_loop('anthropic');self.assertEqual(count,1);self.assertEqual(calls[1]['messages'][-1]['content'][0]['content'][-1]['type'],'image')
 def test_mozg_compacts_screen_and_never_repeats_action(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  store=types.SimpleNamespace(dir=tmp.name,cfg={'settings':{},'devices':[]},add_event=lambda *a:None)
  app=types.SimpleNamespace(store=store,states={},desktop=object(),demo=False)
  cfg={'preset':'mozg','proto':'openai','base':'https://example.test','model':'test','key':'x','noKey':False,'actions':True,'admin':True,'agent':True,'full':True,'agentMode':'full','browser':False,'effort':'','window':10000}
  sent=[]
  def post(c,url,body,headers):
   sent.append(body)
   if len(sent)==1:
    args={'device':'PC','op':'shot','request':'Открой рабочий стол'}
    return {'choices':[{'message':{'tool_calls':[{'id':'1','function':{'name':'windows_desktop','arguments':json.dumps(args)}}]}}]}
   if len(sent)==2:
    args={'device':'PC','op':'click','x':10,'y':10,'request':'Открой рабочий стол'}
    return {'choices':[{'message':{'tool_calls':[{'id':'2','function':{'name':'windows_desktop','arguments':json.dumps(args)}}]}}]}
   raise assistant.AiError('connection lost')
  with patch.object(assistant,'resolved',lambda c:c),patch.object(assistant,'build_system',lambda *a:'x'*18000),patch.object(assistant,'fixed_tokens',lambda *a:(1,1)),patch.object(assistant,'_find_device',lambda *a:{'id':'pc','name':'PC','driver':'windows'}),patch.object(assistant.frankdesktop,'run',return_value=(b'x'*10000,1280,720)) as run,patch.object(assistant,'_post',side_effect=post):
   result=assistant.ask(app,cfg,[{'role':'user','text':'Открой рабочий стол'}])
  self.assertEqual(run.call_count,2);self.assertEqual(len(sent),3)
  self.assertLess(len(json.dumps(sent[1],ensure_ascii=False).encode()),24000)
  self.assertEqual(len(result['shots']),2);self.assertIn('не смог',result['text'])
 def test_mozg_promise_is_not_reported_as_a_task(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  app=types.SimpleNamespace(store=types.SimpleNamespace(dir=tmp.name,cfg={'settings':{},'devices':[]}),states={},desktop=object(),demo=False)
  cfg={'preset':'mozg','proto':'openai','base':'https://example.test','model':'test','key':'x','noKey':False,'actions':True,'admin':True,'agent':True,'full':True,'browser':False,'effort':'','window':10000}
  bodies=[]
  def post(c,url,body,headers):
   bodies.append(body)
   return {'choices':[{'message':{'content':'Сейчас сделаю снимок экрана. Отправляю снимок экрана...'}}]}
  with patch.object(assistant,'resolved',lambda c:c),patch.object(assistant,'build_system',lambda *a:'system'),patch.object(assistant,'fixed_tokens',lambda *a:(1,1)),patch.object(assistant,'_post',side_effect=post):
   result=assistant.ask(app,cfg,[{'role':'user','text':'Получится?'}])
   self.assertIn('ещё не получил',result['text']);self.assertFalse(result['shots'])
   result=assistant.ask(app,cfg,[{'role':'user','text':'Посмотри рабочий стол компьютера PC'}])
   self.assertEqual(bodies[-1]['tool_choice']['function']['name'],'windows_desktop')
   self.assertIn('ещё не получил',result['text'])
  self.assertFalse(assistant._desktop_request('Как открыть рабочий стол?'))
  self.assertFalse(assistant._desktop_request('Не открывай рабочий стол'))
 def test_direct_screenshot_no_model_and_device_ambiguity(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  pc={'id':'pc1','name':'Домашний ПК','driver':'windows','enabled':True}
  store=types.SimpleNamespace(dir=tmp.name,cfg={'settings':{},'devices':[pc]},add_event=lambda *a:None)
  app=types.SimpleNamespace(store=store,states={},desktop=object(),demo=False)
  cfg={'preset':'mozg','proto':'openai','base':'https://example.test','model':'test','key':'x','noKey':False,'actions':True,'admin':True,'agent':True,'full':True,'browser':False,'effort':'','window':10000}
  msg='Мне просто нужно чтоб ты сделал скриншот рабочего стола и отправил мне'
  with patch.object(assistant,'resolved',lambda c:c),patch.object(assistant,'build_system',lambda *a:'system'),patch.object(assistant,'fixed_tokens',lambda *a:(1,1)),patch.object(assistant.frankdesktop,'run',return_value=(b'png',1280,720)) as run,patch.object(assistant,'_post',side_effect=AssertionError('unexpected provider call')):
   result=assistant.ask(app,cfg,[{'role':'user','text':msg}]);self.assertEqual(run.call_count,1);self.assertEqual(len(result['shots']),1)
   store.cfg['devices'].append({'id':'pc2','name':'Второй ПК','driver':'windows'})
   result=assistant.ask(app,cfg,[{'role':'user','text':msg}]);self.assertEqual(run.call_count,1);self.assertIn('Уточни',result['text'])
   result=assistant.ask(app,dict(cfg,admin=False),[{'role':'user','text':msg}]);self.assertEqual(run.call_count,1);self.assertIn('доступ',result['text'])
  self.assertFalse(assistant._desktop_screenshot_only('Сделай скриншот рабочего стола и открой проводник'))
  self.assertFalse(assistant._desktop_screenshot_only('Не делай скриншот рабочего стола'))
  self.assertFalse(assistant._desktop_screenshot_only('Как сделать скриншот рабочего стола?'))
 def test_rejects_unquoted_request(self):
  calls,result,count=self.run_loop(quote='Другая команда');self.assertEqual(count,0);self.assertEqual(result['shots'],[])

if __name__=='__main__': unittest.main()
