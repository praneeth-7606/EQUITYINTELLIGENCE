import time
import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("stock_intelligence.observability.middleware")

class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        start_time = time.time()
        
        logger.info(f"Incoming Request: {request.method} {request.url.path} | assigned trace_id={trace_id}")
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Process-Time-Sec"] = f"{duration:.4f}"
        
        logger.info(f"Completed Request: {request.method} {request.url.path} | status={response.status_code} | duration={duration:.4f}s")
        return response
