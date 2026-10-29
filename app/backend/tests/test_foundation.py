"""Exercise API boundaries against migrated temporary databases, never preview data."""
import hashlib
import os
import uuid
from datetime import timedelta
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, func, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.core.database import get_db
from app.foundation.api import router
from app.foundation.migrate import upgrade, assert_ready, configuration
from app.models import User, ChatThread, Conversation, Message, ChannelAccount, utcnow
from app.scripts.bootstrap_foundation import create_store

PASSWORD = 'foundation-test-password'


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = None
        if os.environ.get('FOUNDATION_TEST_MYSQL_URL'):
            url = make_url(os.environ['FOUNDATION_TEST_MYSQL_URL']).set(database=None)
            self.server = create_engine(url)
            self.database_name = 'foundation_tests_' + uuid.uuid4().hex
            with self.server.begin() as db:
                db.exec_driver_sql(f'CREATE DATABASE `{self.database_name}` CHARACTER SET utf8mb4')
            self.engine = create_engine(url.set(database=self.database_name))
            self.addCleanup(self.cleanup_mysql)
        else:
            self.engine = create_engine('sqlite:///' + str(Path(self.directory.name)/'case.db'), connect_args={'check_same_thread':False, 'timeout':15})
            @event.listens_for(self.engine, 'connect')
            def configure(dbapi, _):
                dbapi.execute('PRAGMA foreign_keys=ON'); dbapi.execute('PRAGMA busy_timeout=15000')
        upgrade(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        with self.sessions.begin() as db:
            self.a = create_store(db,name='Store A',entry_code='store-a',username='agent-a',password=PASSWORD)
            self.b = create_store(db,name='Store B',entry_code='store-b',username='agent-b',password=PASSWORD)
        self.application = FastAPI(); self.application.include_router(router)
        from app.foundation.errors import configure_errors
        configure_errors(self.application)
        def session():
            with self.sessions() as db:yield db
        self.application.dependency_overrides[get_db]=session
        self.client=TestClient(self.application,client=(self.id(),50000))
        self.auth=self.login('agent-a'); self.other=self.login('agent-b')

    def tearDown(self):
        self.client.close(); self.engine.dispose(); self.directory.cleanup()

    def cleanup_mysql(self):
        if self.server is not None:
            self.engine.dispose()
            with self.server.begin() as db:db.exec_driver_sql(f'DROP DATABASE `{self.database_name}`')
            self.server.dispose()
            self.server=None

    def login(self,name):
        r=self.client.post('/api/auth/login',json={'account':name,'password':PASSWORD})
        self.assertEqual(r.status_code,200,r.text)
        return {'Authorization':'Bearer '+r.json()['access_token']}

    def guest(self, store='store-a', visitor='customer-0001', proof='x'*40):
        r=self.client.post('/api/auth/guest-session',json={'entry_code':store,'visitor_id':visitor,'visitor_proof':proof})
        self.assertEqual(r.status_code,200,r.text)
        auth={'Authorization':'Bearer '+r.json()['access_token']}
        r=self.client.post('/api/customer/chat',headers=auth)
        self.assertEqual(r.status_code,200,r.text)
        return auth,r.json()['thread_id'],r.json()['conversation']

    def online(self,auth=None):
        r=self.client.put('/api/agent/presence',headers=auth or self.auth,json={'status':'ONLINE'})
        self.assertEqual(r.status_code,200,r.text)

    def send(self,auth,thread,key='message-0001',content='Hello'):
        return self.client.post(f'/api/customer/threads/{thread}/messages',headers=auth,
                                json={'client_message_id':key,'content':content})

    def claim(self,c,auth=None):
        return self.client.post(f"/api/agent/conversations/{c['id']}/claim",headers=auth or self.auth,
                                json={'expected_epoch':c['reception_epoch']})

    def test_tenant_scoping_and_legacy_routes_disabled(self):
        customer,thread,c=self.guest()
        self.assertEqual(self.client.get('/api/admin/store',headers=self.other).json()['name'],'Store B')
        self.assertEqual(self.client.get('/api/agent/threads',headers=self.other).json()['total'],0)
        self.assertEqual(self.client.get(f"/api/admin/conversations/{c['id']}",headers=self.other).status_code,404)
        self.assertEqual(self.client.get(f'/api/agent/threads/{thread}/messages',headers=self.other).status_code,404)
        self.assertEqual(self.client.get('/api/admin/users/page',headers=self.auth).json()['total'],1)
        self.assertEqual(self.client.get('/api/admin/users/page',headers=customer).status_code,403)
        self.assertEqual(self.client.post('/api/internal/customer-token',json={}).status_code,404)
        self.assertEqual(self.client.post('/api/demo/customer-login').status_code,404)
        self.assertFalse(self.client.get('/health').json()['taobao_orders'])

    def test_account_replacement_logout_and_disabled_staff(self):
        old=self.auth; current=self.login('agent-a')
        self.assertEqual(self.client.get('/api/auth/me',headers=old).status_code,401)
        self.assertEqual(self.client.post('/api/auth/logout',headers=old).status_code,401)
        self.assertEqual(self.client.get('/api/auth/me',headers=current).status_code,200)
        created=self.client.post('/api/admin/users',headers=current,json={'username':'agent-extra','display_name':'Extra','password':PASSWORD})
        self.assertEqual(created.status_code,200,created.text)
        extra=self.login('agent-extra')
        self.assertEqual(self.client.patch(f"/api/admin/users/{created.json()['id']}",headers=current,json={'active':False}).status_code,200)
        self.assertEqual(self.client.post('/api/agent/heartbeat',headers=extra).status_code,401)
        self.assertEqual(self.client.patch(f"/api/admin/users/{self.b['user_id']}",headers=current,json={'active':False}).status_code,404)
        self.assertEqual(self.client.post('/api/admin/users',headers=current,json={'username':'hack','display_name':'Hack','password':PASSWORD,'role':'SUPER_ADMIN'}).status_code,422)
        self.assertEqual(self.client.post('/api/auth/logout',headers=current).status_code,200)
        self.assertEqual(self.client.get('/api/auth/me',headers=current).status_code,401)

    def test_guest_scope_and_proof(self):
        a,thread,c=self.guest()
        b,other,c2=self.guest('store-b')
        self.assertNotEqual(thread,other)
        self.assertEqual(self.client.get(f'/api/customer/threads/{thread}/messages',headers=b).status_code,404)
        self.client.cookies.clear()
        wrong=self.client.post('/api/auth/guest-session',json={'entry_code':'store-a','visitor_id':'customer-0001','visitor_proof':'z'*40})
        self.assertEqual(wrong.status_code,409)
        a2,thread2,c3=self.guest()
        self.assertEqual(thread,thread2);self.assertEqual(c['id'],c3['id'])

    def test_durable_reception_and_reopen_idempotency(self):
        customer,thread,c=self.guest()
        r=self.send(customer,thread);self.assertEqual(r.status_code,200,r.text)
        duplicate=self.send(customer,thread);self.assertEqual(duplicate.json()['message']['id'],r.json()['message']['id'])
        self.assertEqual(self.send(customer,thread,content='different').status_code,409)
        self.assertEqual(self.claim(c).status_code,409) # Online is an explicit business condition.
        self.online();r=self.claim(c);self.assertEqual(r.status_code,200,r.text);c=r.json()
        self.assertEqual(self.client.post(f"/api/agent/conversations/{c['id']}/messages",headers=self.auth,
            json={'client_message_id':'reply-00001','content':'We received your request'}).status_code,200)
        self.client.put('/api/agent/presence',headers=self.auth,json={'status':'OFFLINE'})
        self.assertEqual(self.client.post(f"/api/agent/conversations/{c['id']}/messages",headers=self.auth,
            json={'client_message_id':'reply-00002','content':'Offline staff can finish existing work'}).status_code,200)
        close=self.client.post(f"/api/agent/conversations/{c['id']}/close",headers=self.auth,json={'expected_epoch':c['reception_epoch']})
        self.assertEqual(close.status_code,200,close.text);closed=close.json()
        self.assertEqual(closed['summary_status'],'NONE');self.assertIsNone(closed['consultation_summary'])
        before=self.client.get('/api/agent/threads',headers=self.auth).json()
        self.assertEqual(before['total'],1)
        self.assertEqual(self.send(customer,thread).json()['conversation']['id'],c['id']) # A network retry cannot create another reception.
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Conversation)),1)
        self.online()
        payload={'expected_epoch':closed['reception_epoch'],'request_id':'reopen-00001'}
        new=self.client.post(f"/api/agent/conversations/{c['id']}/reopen",headers=self.auth,json=payload)
        self.assertEqual(new.status_code,200,new.text)
        replay=self.client.post(f"/api/agent/conversations/{c['id']}/reopen",headers=self.auth,json=payload)
        self.assertEqual(replay.json()['id'],new.json()['id'])
        self.assertNotEqual(c['id'],new.json()['id'])
        self.assertEqual(self.client.get('/api/agent/threads',headers=self.auth).json()['total'],1)
        self.assertEqual(self.client.get('/api/admin/conversations',headers=self.auth).json()['total'],1)
        self.assertEqual(self.client.get(f'/api/customer/threads/{thread}/messages',headers=customer).json()['items'][0]['content'],'Hello')
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)),3)
            self.assertEqual(db.get(Conversation,c['id']).status,'CLOSED')
        # Dispose every connection and use a fresh session factory against the same file.
        self.engine.dispose()
        self.assertEqual(self.client.get(f'/api/agent/threads/{thread}/messages',headers=self.auth).json()['items'][-1]['content'],
                         'Offline staff can finish existing work')

    def test_customer_reconsults_and_stale_end_target(self):
        customer,thread,c=self.guest()
        self.send(customer,thread)
        end={'conversation_id':c['id'],'expected_epoch':c['reception_epoch']}
        self.assertEqual(self.client.post(f'/api/customer/threads/{thread}/end',headers=customer,json=end).status_code,200)
        # Reloading the customer page must not create an empty new reception.
        self.assertEqual(self.client.post('/api/customer/chat',headers=customer).json()['conversation']['id'],c['id'])
        fresh=self.send(customer,thread,'message-0002','Another question').json()['conversation']
        self.assertNotEqual(c['id'],fresh['id'])
        self.client.post(f'/api/customer/threads/{thread}/end',headers=customer,json=end)
        with self.sessions() as db:self.assertEqual(db.get(Conversation,fresh['id']).status,'WAITING_USER')

    def test_messages_and_customer_entrances_are_paginated(self):
        customer,thread,c=self.guest()
        for i in range(5):self.assertEqual(self.send(customer,thread,f'message-{i:04d}',f'Question {i}').status_code,200)
        first=self.client.get(f'/api/customer/threads/{thread}/messages?page_size=2',headers=customer).json()
        second=self.client.get(f"/api/customer/threads/{thread}/messages?page_size=2&after_id={first['next_cursor']}",headers=customer).json()
        self.assertTrue(first['has_more']);self.assertEqual(len(second['items']),2)
        self.assertGreater(second['items'][0]['id'],first['items'][-1]['id'])
        self.guest(visitor='customer-0002');self.guest(visitor='customer-0003')
        page=self.client.get('/api/agent/threads?page_size=2',headers=self.auth).json()
        self.assertEqual(page['total'],3);self.assertEqual(len(page['items']),2)
        self.assertEqual(len(self.client.get('/api/agent/threads?page_size=2&page=2',headers=self.auth).json()['items']),1)

    def test_two_staff_can_only_claim_once(self):
        created=self.client.post('/api/admin/users',headers=self.auth,json={'username':'agent-extra','display_name':'Extra','password':PASSWORD})
        self.assertEqual(created.status_code,200,created.text)
        extra=self.login('agent-extra');self.online();self.online(extra)
        _,_,c=self.guest()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda auth:self.claim(c,auth).status_code,[self.auth,extra]))
        self.assertEqual(sorted(statuses),[200,409])
        with self.sessions() as db:
            self.assertIn(db.get(Conversation,c['id']).current_agent_id,[self.a['user_id'],created.json()['id']])

    def test_simultaneous_duplicate_message_and_reopen(self):
        customer,thread,c=self.guest()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.send(customer,thread),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200])
        self.assertEqual(results[0].json()['message']['id'],results[1].json()['message']['id'])
        closed=self.client.post(f'/api/customer/threads/{thread}/end',headers=customer,
            json={'conversation_id':c['id'],'expected_epoch':c['reception_epoch']}).json()
        self.online()
        def request(_):return self.client.post(f"/api/agent/conversations/{c['id']}/reopen",headers=self.auth,
            json={'expected_epoch':closed['reception_epoch'],'request_id':'simultaneous-reopen'})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,range(2)))
        self.assertEqual([r.status_code for r in results],[200,200])
        self.assertEqual(results[0].json()['id'],results[1].json()['id'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Conversation)),2)
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)),1)

    def test_stale_epoch_expired_heartbeat_and_corrupt_pointer_are_rejected(self):
        customer,thread,c=self.guest();self.online()
        with self.sessions.begin() as db:db.get(User,self.a['user_id']).last_heartbeat_at=utcnow()-timedelta(seconds=31)
        self.assertEqual(self.claim(c).json()['detail']['code'],'HEARTBEAT_EXPIRED')
        self.online();wrong=dict(c,reception_epoch=c['reception_epoch']+1)
        self.assertEqual(self.claim(wrong).status_code,409)
        _,_,foreign=self.guest('store-b')
        with self.sessions.begin() as db:db.get(ChatThread,thread).active_conversation_id=foreign['id']
        self.assertEqual(self.send(customer,thread).status_code,409)
        self.assertEqual(self.client.post('/api/customer/chat',headers=customer).status_code,409)
        self.assertEqual(self.client.get('/api/agent/threads',headers=self.auth).json()['total'],0)

    def test_migration_is_versioned_and_preserves_data(self):
        assert_ready(self.engine)
        with self.sessions() as db:before=db.scalar(select(func.count()).select_from(User))
        upgrade(self.engine)
        with self.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(User)),before)
        unknown=create_engine('sqlite://')
        with unknown.begin() as db:db.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
        with self.assertRaises(RuntimeError):upgrade(unknown,adopt_legacy=True)
        with unknown.connect() as db:self.assertNotIn('alembic_version',[x[0] for x in db.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")])
        unknown.dispose()

class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        from alembic import command
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'legacy.db'
        self.engine=create_engine('sqlite:///'+str(self.path))
        command.upgrade(configuration(self.engine),'20261021_01')
        with self.engine.begin() as db:db.exec_driver_sql('DROP TABLE alembic_version')

    def tearDown(self):
        self.engine.dispose();self.directory.cleanup()

    def test_frozen_legacy_rows_survive_and_unmapped_store_cannot_start(self):
        with self.engine.begin() as db:
            db.exec_driver_sql("INSERT INTO tenant (id,name) VALUES (1,'Original shop')")
            db.exec_driver_sql("INSERT INTO channel_account (id,platform_code,name,category,commerce_enabled,active) VALUES (1,'TAOBAO','Original shop','ECOMMERCE',1,1)")
            db.exec_driver_sql("INSERT INTO user (id,tenant_id,kind,user_type,username,display_name,role,active,created_at,updated_at) VALUES (1,1,'GUEST','C','original-customer','Original customer','GUEST',1,'2026-01-01','2026-01-01')")
            db.exec_driver_sql("INSERT INTO conversation (id,tenant_id,user_id,account_id,status,started_at,last_message_at) VALUES (1,1,1,1,'CLOSED','2026-01-01','2026-01-01')")
            db.exec_driver_sql("INSERT INTO message (id,conversation_id,sender_type,content,content_type,delivery_status,citations,created_at) VALUES (1,1,'CUSTOMER','Original message','text','LOCAL','[]','2026-01-01')")
        tables=['tenant','channel_account','user','conversation','message']
        with self.engine.connect() as db:
            columns={name:[c['name'] for c in inspect(db).get_columns(name)] for name in tables}
            original={name:db.exec_driver_sql('SELECT '+','.join('"'+c+'"' for c in columns[name])+' FROM "'+name+'"').all() for name in tables}
        upgrade(self.engine,adopt_legacy=True)
        with self.engine.connect() as db:
            for name in tables:
                rows=db.exec_driver_sql('SELECT '+','.join('"'+c+'"' for c in columns[name])+' FROM "'+name+'"').all()
                self.assertEqual(rows,original[name])
            self.assertFalse(db.exec_driver_sql('PRAGMA foreign_key_check').all())
            self.assertIsNone(db.exec_driver_sql('SELECT tenant_id FROM channel_account').scalar())
        with self.assertRaisesRegex(RuntimeError,'explicit mapping'):assert_ready(self.engine)
        self.assertEqual(len(list(self.path.parent.glob('legacy.db.backup-*'))),1)
        upgrade(self.engine)
        self.assertEqual(len(list(self.path.parent.glob('legacy.db.backup-*'))),1)

    def test_matching_columns_with_changed_type_are_not_silently_adopted(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import String
        with self.engine.begin() as db:
            with Operations.context(MigrationContext.configure(db)) as op:
                with op.batch_alter_table('user') as batch:batch.alter_column('display_name',type_=String(99))
        with self.assertRaisesRegex(RuntimeError,'Unrecognized schema'):upgrade(self.engine,adopt_legacy=True)
        self.assertNotIn('alembic_version',inspect(self.engine).get_table_names())

if __name__=='__main__':unittest.main()
