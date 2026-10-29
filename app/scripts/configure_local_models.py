"""Import previously supplied local credentials into one explicit development store."""
import argparse
import json
import os
from pathlib import Path
import sys
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'var/foundation'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entry-code',required=True)
    parser.add_argument('--seed-demo',action='store_true')
    args=parser.parse_args()
    credentials=dotenv_values(ROOT.parent/'reference/HelpPilot/.env')
    access=json.loads((DATA/'local-access.json').read_text())
    os.environ.update(FOUNDATION_ENABLED='true',DATABASE_URL='sqlite:///'+str(DATA/'service.db'),
        JWT_SECRET=access['jwt_secret'],MODEL_ENCRYPTION_KEY=(DATA/'model-encryption.key').read_text().strip(),
        DASHSCOPE_BASE_URL=credentials.get('DASHSCOPE_BASE_URL') or 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    os.chdir(DATA);sys.path.insert(0,str(ROOT/'backend'))
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models import ChannelAccount,User,Document,KnowledgeCategory
    from app.foundation import model_config as C,model_runtime as M,ai_schemas as S,knowledge as K
    from app.foundation.security import Identity
    with SessionLocal() as db:
        store=db.scalar(select(ChannelAccount).where(ChannelAccount.entry_code==args.entry_code))
        if not store or not store.tenant_id:raise RuntimeError('Explicit development store not found')
        user=db.scalar(select(User).where(User.tenant_id==store.tenant_id,User.username==access['staff_account'],User.active.is_(True)))
        if not user:raise RuntimeError('Development store staff identity not found')
        identity=Identity(user.id,user.tenant_id,'staff',user.session_id,user.session_version)
        current=M.current(db,store.tenant_id)
        if current:
            print(json.dumps({'status':'existing_configuration_preserved','version':current.version}))
        else:
            if not credentials.get('DEEPSEEK_API_KEY') or not credentials.get('DASHSCOPE_API_KEY'):
                raise RuntimeError('Previously supplied credentials are unavailable')
            result=C.save_models(db,identity,S.ModelsSave(expected_version=0,
                dialogue={'provider':'deepseek','model_id':'deepseek-flash','api_key':credentials['DEEPSEEK_API_KEY']},
                embedding={'provider':'dashscope','model_id':'text-embedding-v4','dimension':1024,'api_key':credentials['DASHSCOPE_API_KEY']},
                rerank={'provider':'dashscope','model_id':'qwen3.7-text-rerank','api_key':credentials['DASHSCOPE_API_KEY']}))
            print(json.dumps({'status':'configured_and_verified','version':result['version']}))
        if args.seed_demo:
            if db.scalar(select(Document.id).where(Document.tenant_id==store.tenant_id,Document.title=='示例·知识检索验证')):
                print('Existing demonstration knowledge preserved.');return
            with K.writing(db,identity):
                category=db.scalar(select(KnowledgeCategory).where(KnowledgeCategory.tenant_id==store.tenant_id,
                    KnowledgeCategory.name=='联调示例（可停用）'))
                if not category:
                    category=KnowledgeCategory(tenant_id=store.tenant_id,name='联调示例（可停用）',
                        description='验证真实知识检索链路，不代表店铺售后承诺。',created_by_user_id=user.id,updated_by_user_id=user.id)
                    db.add(category);db.flush()
                category_id=category.id
            result=K.publish(db,identity,S.PublishInput(title='示例·知识检索验证',category_id=category_id,
                content='这是一份联调知识，用于验证真实检索链路，不代表店铺售后承诺。\n\n问：联调验证口令是什么？\n答：联调验证口令是 QH-2026-AI。\n\n问：示例用于什么？\n答：验证本店知识发布、语义检索、重排、真实回答和来源展示。'))
            print(json.dumps({'demonstration_document_id':result['document_id'],'job_id':result['job']['id']}))


if __name__=='__main__':main()
