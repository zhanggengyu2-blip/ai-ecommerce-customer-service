import uuid
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def configure_errors(app):
    @app.middleware('http')
    async def request_identity(request, call_next):
        request.state.request_id=uuid.uuid4().hex
        response=await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Validation errors otherwise echo the rejected input, including API Keys.
        return JSONResponse(status_code=422,content={'detail':{'code':'INVALID_INPUT','message':'请检查填写内容',
            'request_id':getattr(request.state,'request_id',''),
            'errors':[{'field':'.'.join(str(i) for i in e['loc']),'message':e['msg']} for e in exc.errors()]}})

    @app.exception_handler(HTTPException)
    async def business(request, exc):
        detail=exc.detail if isinstance(exc.detail,dict) else {'code':'HTTP_'+str(exc.status_code),'message':exc.detail}
        return JSONResponse(status_code=exc.status_code,headers=exc.headers,
            content={'detail':detail|{'request_id':getattr(request.state,'request_id','')}})
