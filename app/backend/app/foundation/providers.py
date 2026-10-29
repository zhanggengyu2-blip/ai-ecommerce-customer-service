"""Role-scoped HTTP adapters. Only explicitly supplied, decrypted credentials are used."""
import json
import math
import httpx
from app.providers.ai import ProviderError


def post(role, path, payload, trace, kind, name, *, native=False):
    key=role['api_key'];trace.secrets.add(key)
    base=role['endpoint'].removesuffix('/compatible-mode/v1') if native else role['endpoint']
    for attempt in range(1,3):
        try:
            with trace.step(kind,name,data={'request':payload},model=role['model_id'],remote=True,attempt=attempt) as node:
                try:
                    with httpx.Client(timeout=httpx.Timeout(60,connect=5),follow_redirects=False) as client:
                        response=client.post(base+path,headers={'Authorization':'Bearer '+key},json=payload)
                except (httpx.TimeoutException,httpx.NetworkError):
                    raise ProviderError('模型服务连接失败','network_error') from None
                except httpx.HTTPError:
                    raise ProviderError('模型服务请求失败','request_error') from None
                if response.status_code!=200:
                    raise ProviderError('模型服务未接受请求','http_'+str(response.status_code),response.status_code)
                try:data=response.json()
                except ValueError:raise ProviderError('模型服务返回格式错误','invalid_response') from None
                if not isinstance(data,dict) or data.get('code'):
                    raise ProviderError('模型服务返回错误','invalid_response')
                node['usage']=data.get('usage') if isinstance(data.get('usage'),dict) else {}
                node['output']={'usage':node['usage'],'request_id':str(data.get('request_id') or data.get('id') or '')[:128]}
                node['output']['response']=({'vector_count':len(data.get('data',[])),'dimension':role.get('dimension')}
                    if kind=='ai.embed' else data)
                return data
        except ProviderError as exc:
            if attempt==1 and exc.code=='network_error':continue
            raise


def chat(role, messages, trace, *, kind='llm.generate', name='生成知识回复', max_tokens=1200):
    payload={'model':role['model_id'],'messages':messages,'temperature':0,'max_tokens':max_tokens,
             'response_format':{'type':'json_object'}}
    if role['provider']=='deepseek':payload['thinking']={'type':'disabled'}
    else:payload['enable_thinking']=False
    data=post(role,'/chat/completions',payload,trace,kind,name)
    try:
        choice=data['choices'][0];content=choice['message']['content']
        if choice.get('finish_reason') not in (None,'stop') or not isinstance(content,str):raise ValueError()
        value=json.loads(content)
        if not isinstance(value,dict):raise ValueError()
        return value
    except (KeyError,TypeError,ValueError,IndexError):
        raise ProviderError('模型未返回完整结构化结果','invalid_response') from None


def embed(role, texts, trace):
    vectors=[];dimension=role['dimension']
    for start in range(0,len(texts),10):
        batch=texts[start:start+10]
        data=post(role,'/embeddings',{'model':role['model_id'],'input':batch,'dimensions':dimension,'encoding_format':'float'},
                  trace,'ai.embed','生成检索向量')
        try:
            items=sorted(data['data'],key=lambda x:x['index'])
            valid=([item['index'] for item in items]==list(range(len(batch)))
                and all(isinstance(item['index'],int) and not isinstance(item['index'],bool) for item in items))
            result=[item['embedding'] for item in items]
            valid=valid and all(isinstance(v,list) and len(v)==dimension and all(
                isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v)
                and sum(x*x for x in v)>0 for v in result)
            if not valid:raise ValueError()
            vectors.extend(result)
        except (KeyError,TypeError,ValueError):
            raise ProviderError('向量维度或内容不正确','invalid_embedding') from None
    return vectors


def rerank(role, query, documents, trace):
    if not documents:return []
    data=post(role,'/api/v1/services/rerank/text-rerank/text-rerank',{
        'model':role['model_id'],'input':{'query':query,'documents':documents},
        'parameters':{'top_n':len(documents)}},trace,'ai.rerank','知识相关度重排',native=True)
    try:
        rows=data['output']['results'];indices=[r['index'] for r in rows]
        valid=(isinstance(rows,list) and len(rows)==len(documents) and len(set(indices))==len(indices)
            and all(isinstance(i,int) and not isinstance(i,bool) and 0<=i<len(documents) for i in indices)
            and all(isinstance(r['relevance_score'],(int,float)) and not isinstance(r['relevance_score'],bool)
                and math.isfinite(r['relevance_score']) and 0<=r['relevance_score']<=1 for r in rows))
        if not valid:raise ValueError()
        return sorted([{'index':r['index'],'score':float(r['relevance_score'])} for r in rows],key=lambda r:r['score'],reverse=True)
    except (KeyError,TypeError,ValueError):
        raise ProviderError('重排相关度不完整，不能应用 Score 阈值','invalid_rerank') from None


def check(role_name, role, trace):
    if role_name=='dialogue':
        result=chat(role,[{'role':'system','content':'这是接口校验。仅返回 JSON 对象 {"ok": true}。'},
                          {'role':'user','content':'请返回校验结果 JSON。'}],trace,kind='llm.check',name='对话模型校验',max_tokens=64)
        if result.get('ok') is not True:raise ProviderError('对话配置校验未通过','invalid_response')
    elif role_name=='embedding':embed(role,['店铺客服知识检索配置校验'],trace)
    else:rerank(role,'如何查询尺码',['可以查看商品尺码表。','这是模型配置校验，与天气无关。'],trace)
