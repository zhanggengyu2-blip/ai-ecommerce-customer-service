"""Business and race tests use a controlled provider; live probes are separate."""
import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select, func
import test_foundation as foundation
from app.config.settings import settings
from app.models import (ConfigVersion, AiGeneration, KnowledgeJob, Document, DocumentVersion, Chunk,
    Message, Conversation, QuestionTrace, QuestionTraceNode, QuestionTracePayload, utcnow)
from app.foundation import workers as W, model_runtime as M, knowledge as K


class ModelsKnowledgeTests(unittest.TestCase):
    login=foundation.FoundationTests.login
    guest=foundation.FoundationTests.guest
    online=foundation.FoundationTests.online
    send=foundation.FoundationTests.send
    claim=foundation.FoundationTests.claim
    cleanup_mysql=foundation.FoundationTests.cleanup_mysql

    def setUp(self):
        self.previous_key=os.environ.get('MODEL_ENCRYPTION_KEY')
        os.environ['MODEL_ENCRYPTION_KEY']=Fernet.generate_key().decode();settings.cache_clear()
        foundation.FoundationTests.setUp(self)
        self.calls=[];self.score=.95;self.fail_embed=False;self.bad_vector=False;self.bad_rerank=False;self.answer_hook=None;self.embed_hook=None
        self.adapter=patch('app.foundation.providers.httpx.Client')
        transport=self.adapter.start().return_value
        transport.__enter__.return_value=transport
        transport.post.side_effect=self.provider
        self.keys={'dialogue':'fixture-deepseek-key-secret-123456','embedding':'fixture-embedding-key-secret-123456','rerank':'fixture-rerank-key-secret-123456'}

    def tearDown(self):
        self.adapter.stop();foundation.FoundationTests.tearDown(self)
        if self.previous_key is None:os.environ.pop('MODEL_ENCRYPTION_KEY',None)
        else:os.environ['MODEL_ENCRYPTION_KEY']=self.previous_key
        settings.cache_clear()

    def provider(self,url,*,headers,json:dict,**kwargs):
        payload=json;self.calls.append((str(url),payload))
        if str(url).endswith('/embeddings'):
            if self.embed_hook:
                hook=self.embed_hook;self.embed_hook=None;hook()
            if self.fail_embed:return httpx.Response(503,json={'message':'unavailable'})
            value={'data':[{'index':i,'embedding':[1.0]+[0.0]*(payload['dimensions']-1)} for i,_ in enumerate(payload['input'])],
                   'usage':{'prompt_tokens':7,'total_tokens':7}}
            if self.bad_vector:value['data'][0]['embedding'].pop()
        elif '/rerank/' in str(url):
            value={'output':{'results':[{'index':i,'relevance_score':self.score} for i,_ in enumerate(payload['input']['documents'])]},'usage':{'total_tokens':9}}
            if self.bad_rerank:
                for row in value['output']['results']:row.pop('relevance_score')
        else:
            system=payload['messages'][0]['content'];raw=payload['messages'][-1]['content']
            if '接口校验' in system:value={'ok':True}
            elif '概括' in system:value={'purpose':'用于回答店铺测试知识问题。'}
            elif '路由器' in system:
                request=__import__('json').loads(raw);value={'action':'KNOWLEDGE','query':request['question'],'document_ids':[]}
            else:
                request=__import__('json').loads(raw)
                if self.answer_hook:
                    hook=self.answer_hook;self.answer_hook=None;hook()
                value={'supported':True,'answer':request['knowledge'][0]['content'],'source_ids':[request['knowledge'][0]['id']]}
            value={'choices':[{'message':{'content':__import__('json').dumps(value,ensure_ascii=False)},'finish_reason':'stop'}],
                   'usage':{'prompt_tokens':11,'completion_tokens':3,'total_tokens':14}}
        return httpx.Response(200,json=value)

    def models_body(self,version=0,dimension=1024,keys=True):
        return {'expected_version':version,
            'dialogue':{'provider':'deepseek','model_id':'deepseek-flash','api_key':self.keys['dialogue'] if keys else ''},
            'embedding':{'provider':'dashscope','model_id':'text-embedding-v4','dimension':dimension,'api_key':self.keys['embedding'] if keys else ''},
            'rerank':{'provider':'dashscope','model_id':'qwen3.7-text-rerank','api_key':self.keys['rerank'] if keys else ''}}

    def configure(self,auth=None):
        response=self.client.put('/api/admin/settings/models',headers=auth or self.auth,json=self.models_body())
        self.assertEqual(response.status_code,200,response.text)

    def category(self,name='Test knowledge',auth=None):
        r=self.client.post('/api/admin/knowledge-categories',headers=auth or self.auth,json={'name':name,'description':'Test purposes'})
        self.assertEqual(r.status_code,200,r.text);return r.json()['id']

    def publish(self,category=None,text='知识验证口令是 QH-TEST。',document=None,**extra):
        category=category or self.category()
        payload={'title':'验证知识','category_id':category,'content':text}
        if document:
            current=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
            payload|={'document_id':document,'expected_revision':current['revision']}
        payload.update(extra)
        r=self.client.post('/api/admin/documents/publish',headers=self.auth,json=payload)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def finish_publish(self,result):
        self.assertTrue(W.run_once(self.sessions))
        job=self.client.get('/api/admin/knowledge/jobs/'+result['job']['id'],headers=self.auth).json()
        self.assertEqual(job['status'],'DONE',job)

    def enabled(self):
        self.configure();category=self.category();result=self.publish(category);self.finish_publish(result)
        r=self.client.put('/api/admin/settings/reception',headers=self.auth,json={'enabled':True,'expected_version':0})
        self.assertEqual(r.status_code,200,r.text);return category,result['document_id']

    def test_keys_encrypted_scoped_redacted_and_provider_change_requires_key(self):
        self.configure()
        response=self.client.get('/api/admin/settings/models',headers=self.auth)
        for key in self.keys.values():self.assertNotIn(key,response.text)
        with self.sessions() as db:
            row=M.current(db,self.a['tenant_id']);serialized=__import__('json').dumps(row.value)
            for key in self.keys.values():self.assertNotIn(key,serialized)
            self.assertEqual(M.runtime(self.a['tenant_id'],row.value)['dialogue']['api_key'],self.keys['dialogue'])
            with self.assertRaises(Exception):M.unseal(self.b['tenant_id'],'dialogue',row.value['dialogue']['key_ciphertext'])
        before=len(self.calls)
        self.assertEqual(self.client.put('/api/admin/settings/models',headers=self.auth,json=self.models_body(1,keys=False)).status_code,200)
        self.assertEqual(len(self.calls),before) # Verified fingerprint comes only from a successful server check.
        change=self.models_body(2,keys=False);change['dialogue'].update(provider='dashscope',model_id='qwen-plus')
        self.assertEqual(self.client.put('/api/admin/settings/models',headers=self.auth,json=change).status_code,422)
        self.assertEqual(len(self.calls),before)
        invalid=self.models_body(2);invalid['dialogue']['endpoint']='https://attacker.invalid'
        invalid['dialogue']['api_key']='secret-rejected-input-123456'
        r=self.client.put('/api/admin/settings/models',headers=self.auth,json=invalid)
        self.assertEqual(r.status_code,422);self.assertNotIn('secret-rejected-input',r.text)
        self.assertEqual(self.client.get('/api/admin/settings/models',headers=self.other).json()['version'],0)
        customer,_,_=self.guest()
        self.assertEqual(self.client.get('/api/admin/settings/models',headers=customer).status_code,403)

    def test_publish_recall_auto_reply_and_test_usage_are_separate(self):
        _,document=self.enabled();customer,thread,c=self.guest()
        self.assertEqual(c['status'],'AI_ACTIVE')
        sent=self.send(customer,thread,content='知识验证口令是什么？');self.assertEqual(sent.status_code,200)
        self.assertTrue(W.run_once(self.sessions))
        rows=self.client.get(f'/api/customer/threads/{thread}/messages',headers=customer).json()['items']
        self.assertEqual(len(rows),2);self.assertEqual(rows[-1]['sender_type'],'AI')
        self.assertEqual(rows[-1]['citations'][0]['document_id'],document)
        first_usage=self.client.get(f"/api/agent/conversations/{c['id']}/usage",headers=self.auth).json()
        self.assertTrue(first_usage['complete']);self.assertEqual(first_usage['call_count'],4)
        recall=self.client.post('/api/admin/recall-tests',headers=self.auth,json={'query':'知识验证口令是什么？'})
        self.assertEqual(recall.status_code,200,recall.text);self.assertEqual(len(recall.json()['items']),1)
        self.assertEqual(self.client.get(f"/api/agent/conversations/{c['id']}/usage",headers=self.auth).json(),first_usage)
        trace=self.client.get('/api/admin/traces/'+rows[-1]['trace_id'],headers=self.auth)
        self.assertEqual(trace.status_code,200,trace.text)
        self.assertEqual(self.client.get('/api/admin/traces/'+rows[-1]['trace_id'],headers=self.other).status_code,404)
        for key in self.keys.values():self.assertNotIn(key,trace.text)
        self.assertEqual(self.send(customer,thread,content='知识验证口令是什么？').json()['message']['id'],sent.json()['message']['id'])
        self.assertFalse(W.run_once(self.sessions))

    def test_human_claim_during_model_call_discards_late_answer(self):
        self.enabled();customer,thread,c=self.guest();self.online()
        self.send(customer,thread,content='知识验证口令？')
        self.answer_hook=lambda:self.assertEqual(self.claim(c).status_code,200)
        W.run_once(self.sessions)
        with self.sessions() as db:
            self.assertEqual(db.get(Conversation,c['id']).status,'HUMAN_ACTIVE')
            self.assertEqual(db.scalar(select(func.count()).select_from(Message).where(Message.sender_type=='AI')),0)
            self.assertEqual(db.scalar(select(AiGeneration.status)),'SUPERSEDED')

    def test_newer_question_and_policy_disable_fence_old_result(self):
        self.enabled();customer,thread,c=self.guest();self.send(customer,thread,content='第一条问题')
        self.answer_hook=lambda:self.assertEqual(self.send(customer,thread,'message-0002','第二条问题').status_code,200)
        W.run_once(self.sessions)
        with self.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Message).where(Message.sender_type=='AI')),0)
        self.answer_hook=lambda:self.assertEqual(self.client.put('/api/admin/settings/reception',headers=self.auth,
            json={'enabled':False,'expected_version':1}).status_code,200)
        W.run_once(self.sessions)
        with self.sessions() as db:
            self.assertEqual(db.get(Conversation,c['id']).status,'WAITING_USER')
            self.assertEqual(db.scalar(select(func.count()).select_from(Message).where(Message.sender_type=='AI')),0)

    def test_low_rerank_score_does_not_bypass_threshold(self):
        self.enabled();self.score=.01;customer,thread,c=self.guest()
        self.send(customer,thread,content='问题');W.run_once(self.sessions)
        with self.sessions() as db:self.assertEqual(db.get(Conversation,c['id']).status,'WAITING_USER')
        self.assertFalse(any('生成知识回复' in str(call) for call in self.calls))
        r=self.client.post('/api/admin/recall-tests',headers=self.auth,json={'query':'问题'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['items'],[])

    def test_invalid_vectors_and_missing_scores_are_rejected(self):
        category,document=self.enabled();self.bad_vector=True
        result=self.publish(category,document=document,text='不能发布错误维度的知识。');W.run_once(self.sessions)
        detail=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
        self.assertEqual(detail['candidate']['status'],'FAILED');self.assertEqual(detail['published']['version'],1)
        self.bad_vector=False;self.bad_rerank=True
        r=self.client.post('/api/admin/recall-tests',headers=self.auth,json={'query':'验证口令'})
        self.assertEqual(r.status_code,502,r.text)
        customer,thread,c=self.guest();self.send(customer,thread,content='验证口令');W.run_once(self.sessions)
        with self.sessions() as db:self.assertEqual(db.get(Conversation,c['id']).status,'WAITING_USER')

    def test_knowledge_disabled_during_generation_cannot_be_cited(self):
        _,document=self.enabled();customer,thread,c=self.guest();self.send(customer,thread,content='验证口令')
        def disable():
            row=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
            self.assertEqual(self.client.patch(f'/api/admin/documents/{document}',headers=self.auth,
                json={'expected_revision':row['revision'],'enabled':False}).status_code,200)
        self.answer_hook=disable;W.run_once(self.sessions)
        with self.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Message).where(Message.sender_type=='AI')),0)
        W.run_once(self.sessions)
        with self.sessions() as db:
            self.assertEqual(db.get(Conversation,c['id']).status,'WAITING_USER')
            self.assertTrue(all(not m.citations for m in db.scalars(select(Message).where(Message.sender_type=='AI')).all()))

    def test_missing_trace_storage_is_not_reported_as_complete_zero_usage(self):
        self.enabled();customer,thread,c=self.guest();self.send(customer,thread)
        self.online();self.answer_hook=lambda:self.assertEqual(self.claim(c).status_code,200)
        def unavailable(trace,fn):trace.errors.append('StorageUnavailable')
        with patch('app.foundation.trace_store.Trace._write',new=unavailable):W.run_once(self.sessions)
        usage=self.client.get(f"/api/agent/conversations/{c['id']}/usage",headers=self.auth).json()
        self.assertFalse(usage['complete'])

    def test_failed_publication_and_failed_vector_change_preserve_usable_data(self):
        category,document=self.enabled()
        old=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()['published']['id']
        result=self.publish(category,text='新版知识内容。',document=document);self.fail_embed=True
        W.run_once(self.sessions)
        detail=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
        self.assertEqual(detail['published']['id'],old);self.assertEqual(detail['candidate']['status'],'FAILED')
        self.fail_embed=False
        changed=self.client.put('/api/admin/settings/models',headers=self.auth,json=self.models_body(1,512,False))
        self.assertEqual(changed.status_code,200,changed.text);self.assertTrue(changed.json()['preparing'])
        self.assertEqual(self.client.get('/api/admin/settings/models',headers=self.auth).json()['version'],1)
        self.fail_embed=True;W.run_once(self.sessions)
        config=self.client.get('/api/admin/settings/models',headers=self.auth).json()
        self.assertEqual(config['version'],1);self.assertEqual(config['models']['embedding']['dimension'],1024)
        self.assertEqual(config['operation']['status'],'FAILED')

    def test_vector_switch_is_atomic_and_recovers_concurrent_publication(self):
        category,document=self.enabled()
        response=self.client.put('/api/admin/settings/models',headers=self.auth,json=self.models_body(1,512,False))
        self.assertTrue(response.json()['preparing'])
        self.embed_hook=lambda:self.publish(category,text='第二篇知识。',title='第二篇知识')
        W.run_once(self.sessions)
        self.assertEqual(self.client.get('/api/admin/settings/models',headers=self.auth).json()['version'],1)
        W.run_once(self.sessions);W.run_once(self.sessions)
        config=self.client.get('/api/admin/settings/models',headers=self.auth).json()
        self.assertEqual(config['models']['embedding']['dimension'],512)
        with self.sessions() as db:
            spaces={c.embedding_space for c in db.scalars(select(Chunk)).all()}
            self.assertEqual(len(spaces),1)
            self.assertTrue(all(len(c.embedding)==512 for c in db.scalars(select(Chunk)).all()))

    def test_dates_restore_scope_upload_and_retrieval_validation(self):
        self.configure();category=self.category();first=self.publish(category);self.finish_publish(first)
        document=first['document_id'];future=utcnow()+timedelta(days=3)
        second=self.publish(category,document=document,text='计划生效知识。',effective_from=future.isoformat(),effective_until=(future+timedelta(days=1)).isoformat())
        self.finish_publish(second)
        with self.sessions() as db:
            doc=db.get(Document,document)
            self.assertEqual(K.active_version(db,doc).version,1)
            self.assertEqual(K.active_version(db,doc,now=future+timedelta(hours=1)).version,2)
            self.assertIsNone(K.active_version(db,doc,now=future+timedelta(days=2)))
        d=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
        restored=self.client.post(f'/api/admin/documents/{document}/restore-previous',headers=self.auth,json={'expected_revision':d['revision']})
        self.assertEqual(restored.status_code,200,restored.text);self.finish_publish(restored.json())
        d=self.client.get(f'/api/admin/documents/{document}',headers=self.auth).json()
        self.assertIsNone(d['published']['effective_from']);self.assertEqual(d['published']['content'],'知识验证口令是 QH-TEST。')
        self.assertEqual(self.client.get(f'/api/admin/documents/{document}',headers=self.other).status_code,404)
        self.assertEqual(self.client.post('/api/admin/recall-tests',headers=self.other,json={'query':'测试','category_id':category}).status_code,409)
        for score in [None,'0.3',True,-.1,1.1]:
            r=self.client.put('/api/admin/settings/retrieval',headers=self.auth,json={'expected_version':0,'min_score':score,'final_top_k':5})
            self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.client.put('/api/admin/settings/retrieval',headers=self.auth,json={'expected_version':0,'min_score':0,'final_top_k':10}).status_code,200)
        self.assertEqual(self.client.post('/api/admin/knowledge/upload-text',headers=self.auth,files={'file':('bad.pdf',b'pdf','application/pdf')}).status_code,415)
        self.assertEqual(self.client.post('/api/admin/knowledge/upload-text',headers=self.auth,files={'file':('bad.txt',b'\xff\x00','text/plain')}).status_code,422)
        good=self.client.post('/api/admin/knowledge/upload-text',headers=self.auth,files={'file':('note.md','知识正文'.encode(),'text/plain')})
        self.assertEqual(good.status_code,200,good.text)

    def test_expired_worker_lease_and_summary_usage_exclusion(self):
        self.enabled();customer,thread,c=self.guest();self.send(customer,thread)
        old=W.claim_one(self.sessions,AiGeneration)
        with self.sessions.begin() as db:db.get(AiGeneration,old[0]).lease_until=utcnow()-timedelta(seconds=1)
        new=W.claim_one(self.sessions,AiGeneration);self.assertNotEqual(old[1],new[1])
        W.run_reply(self.sessions,*old);W.run_reply(self.sessions,*new)
        usage=self.client.get(f"/api/agent/conversations/{c['id']}/usage",headers=self.auth).json()
        with self.sessions.begin() as db:
            t=QuestionTrace(trace_id='summary-usage-test',tenant_id=self.a['tenant_id'],account_id=self.a['account_id'],
                conversation_id=c['id'],user_id=self.a['user_id'],query='summary',kind='summary',status='FAILED')
            db.add(t);db.flush()
            db.add(QuestionTraceNode(trace_id=t.trace_id,conversation_id=c['id'],sequence=1,node_type='llm.summary',name='summary',
                location='remote_ai',status='FAILED',usage={}))
        self.assertEqual(self.client.get(f"/api/agent/conversations/{c['id']}/usage",headers=self.auth).json(),usage)


if __name__=='__main__':unittest.main()
