import os
import time
import logging
import shutil
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.models import APIResponse, ChatRequest
from app.agents.graph import app_graph
from app.config import settings
from app.auth.service import get_current_user
from app.observability.tracer import AgentTracer
from app.privacy import mask_free_text, safe_user_visible_error
from app.db_ops import (
    save_file_metadata, get_or_create_session, save_chat_message,
    save_report, save_portfolio_transactions
)

logger = logging.getLogger("stock_intelligence.router")
router = APIRouter()

# Data directory path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def get_user_file_path(user_id: str) -> str:
    """Returns a user-specific Excel file path to prevent multi-user collisions."""
    return os.path.join(DATA_DIR, f"portfolio_{user_id}.xlsx")


def write_workflow_log(
    message: str = None,
    selected_agent: str = None,
    response: APIResponse = None,
    errors: list = None
):
    try:
        from datetime import datetime
        logs_dir = os.path.join(PROJECT_ROOT, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file_path = os.path.join(logs_dir, "query_workflows.log")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query_text = mask_free_text(message) if message else f"[Direct Agent Call: {selected_agent}]"
        agent_used = response.agent_used if response and response.agent_used else (selected_agent or "None")
        success_str = "SUCCESS" if response and response.success else "FAILED"
        exec_time = response.execution_time if response else 0.0
        
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"TIMESTAMP:      {timestamp}\n")
            f.write(f"STATUS:         {success_str}\n")
            f.write(f"USER QUERY:     {query_text}\n")
            f.write(f"AGENT INVOLVED: {agent_used}\n")
            f.write(f"EXECUTION TIME: {exec_time}s\n")
            if errors:
                f.write(f"ERRORS:         {mask_free_text(', '.join(errors))}\n")
            f.write("-" * 80 + "\n")
            f.write("REASONING PLAN / AGENT STEPS:\n")
            f.write(f"{response.agent_plan if response and response.agent_plan else 'No agent plan generated.'}\n")
            f.write("-" * 80 + "\n")
            f.write("SUMMARY:\n")
            f.write(f"{mask_free_text(response.summary) if response else 'No summary generated.'}\n")
            if response and response.insights:
                f.write("-" * 80 + "\n")
                f.write("INSIGHTS:\n")
                for ins in response.insights:
                    f.write(f"- {mask_free_text(ins)}\n")
            f.write("=" * 80 + "\n\n")
    except Exception as log_ex:
        logger.error(f"Failed to write query workflow log: {log_ex}")


async def run_workflow_on_file(
    current_user: dict,
    request: Request,
    selected_agent: str = None,
    message: str = None,
    passed_session_id: Optional[str] = None
) -> APIResponse:
    """
    Helper to run the LangGraph workflow on the user's uploaded file.
    Instrumented with AgentTracer and MongoDB data persistence.
    """
    start_time = time.time()
    user_id = str(current_user["_id"])
    username = current_user["username"]
    
    # ── Initialize Trace Observability ────────────────────────────────────────
    session_id = await get_or_create_session(passed_session_id, user_id, message or f"Direct Call: {selected_agent}")
    
    # Resolve the file associated with this session if it exists
    from app.db import chat_sessions_col, files_col
    import bson
    user_file_path = None
    file_id = None
    try:
        session_doc = await chat_sessions_col().find_one({"_id": bson.ObjectId(session_id), "user_id": user_id})
        if session_doc and "file_id" in session_doc:
            file_id = str(session_doc["file_id"])
            file_doc = await files_col().find_one({"_id": bson.ObjectId(session_doc["file_id"])})
            if file_doc:
                user_file_path = file_doc["file_path"]
    except Exception as e:
        logger.error(f"Error resolving file for session: {e}")
        
    if not user_file_path:
        # Fallback to the legacy path
        user_file_path = os.path.join(DATA_DIR, f"portfolio_{user_id}.xlsx")
    
    tracer = AgentTracer(
        user_id=user_id,
        username=username,
        session_id=session_id,
        query=message or f"Direct Call: {selected_agent}",
        selected_agent=selected_agent
    )
    request.state.trace_id = tracer.trace_id
    
    # Immediately persist the trace to database as "running" for the live sessions portal!
    await tracer.persist()
    
    portfolio_required_agents = ["portfolio_agent", "pnl_agent", "dividend_agent"]
    file_missing = not os.path.exists(user_file_path)
    
    # Verify file existence for portfolio-based actions
    if selected_agent in portfolio_required_agents and file_missing:
        execution_time = time.time() - start_time
        response = APIResponse(
            success=False,
            execution_time=round(execution_time, 4),
            agent_used=selected_agent,
            summary="No Excel file uploaded yet. Please upload your stock transaction spreadsheet first.",
            insights=[],
            structured_data={}
        )
        write_workflow_log(message, selected_agent, response)
        
        tracer.finalize(summary=response.summary, agent_used=selected_agent, status="failed")
        await tracer.persist()
        return response

    # Load custom mapping plan if it exists
    plan = None
    candidate_plan_paths = []
    if file_id:
        candidate_plan_paths.append(os.path.join(DATA_DIR, f"mapping_plan_{user_id}_{file_id}.json"))
    candidate_plan_paths.append(os.path.join(DATA_DIR, f"mapping_plan_{user_id}.json"))
    for plan_path in candidate_plan_paths:
        if os.path.exists(plan_path):
            try:
                with open(plan_path, "r", encoding="utf-8") as pf:
                    plan = json.load(pf)
                break
            except Exception as pe:
                logger.error(f"Failed to load saved mapping plan from {plan_path}: {pe}")

    # Initialize Graph State with Auth & Observability contexts
    actual_file_path = user_file_path if os.path.exists(user_file_path) else None
    state = {
        "uploaded_file": actual_file_path,
        "portfolio_dataframe": None,
        "holding_timeline": None,
        "selected_agent": selected_agent,
        "messages": [HumanMessage(content=message)] if message else [],
        "result": None,
        "errors": [],
        "tracer": tracer,
        "user_id": user_id,
        "session_id": session_id
    }
    if plan:
        state["mapping_plan"] = plan

    try:
        logger.info(f"Invoking graph workflow with selected_agent={selected_agent} (async)")
        # Run workflow asynchronously using ainvoke
        final_state = await app_graph.ainvoke(state)
        execution_time = time.time() - start_time
        
        errors = final_state.get("errors", [])
        if errors:
            logger.warning(f"Workflow encountered errors: {errors}")

        result = final_state.get("result")
        if not result:
            response = APIResponse(
                success=False,
                execution_time=round(execution_time, 4),
                agent_used=final_state.get("selected_agent"),
                summary="The agent completed the request but did not generate a result.",
                insights=[],
                structured_data={}
            )
            write_workflow_log(message, selected_agent, response, errors)
            
            tracer.finalize(summary=response.summary, agent_used=response.agent_used, status="failed")
            await tracer.persist()
            return response

        response = APIResponse(
            success=True,
            execution_time=round(execution_time, 4),
            agent_used=final_state.get("selected_agent"),
            agent_plan=result.get("agent_plan"),
            summary=result.get("summary", ""),
            insights=result.get("insights", []),
            structured_data=result.get("structured_data", {})
        )
        write_workflow_log(message, selected_agent, response, errors)
        
        # ── MongoDB Data Persistence ──────────────────────────────────────────
        # 1. Save chat messages if this was a user query
        if message:
            await save_chat_message(session_id, user_id, "user", message)
        await save_chat_message(
            session_id, user_id, "agent", response.summary,
            response.agent_used, response.structured_data, response.insights
        )
        
        # 2. Save snapshot report
        if response.agent_used:
            report_type = response.agent_used.replace("_agent", "")
            await save_report(user_id, session_id, report_type, response.summary, response.structured_data)
            
        # 3. Save portfolio transactions on successful load/refresh
        df_records = final_state.get("portfolio_dataframe")
        if df_records and response.agent_used == "portfolio_agent":
            await save_portfolio_transactions(user_id, df_records, response.structured_data.get("portfolio_summary", {}))

        # ── Finalize Trace ────────────────────────────────────────────────────
        tracer.finalize(
            summary=response.summary,
            agent_used=response.agent_used or selected_agent,
            result_size_bytes=len(response.model_dump_json()),
            status="success"
        )
        await tracer.persist()
        
        return response

    except Exception as e:
        logger.error(f"Failed to execute graph workflow: {e}", exc_info=True)
        execution_time = time.time() - start_time
        response = APIResponse(
            success=False,
            execution_time=round(execution_time, 4),
            agent_used=selected_agent,
            summary=f"An error occurred during workflow execution: {str(e)}",
            insights=[],
            structured_data={}
        )
        write_workflow_log(message, selected_agent, response, [str(e)])
        
        tracer.log_error(e)
        tracer.finalize(summary=response.summary, agent_used=selected_agent, status="failed")
        await tracer.persist()
        return response


@router.post("/upload", response_model=APIResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    mapping_plan: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    new_project_name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Saves the uploaded Excel file. Parses it immediately to validate columns
    and structures before acknowledging success. Saves metadata to MongoDB.
    """
    start_time = time.time()
    user_id = str(current_user["_id"])
    username = current_user.get("username") or current_user.get("email") or "unknown"
    tracer = AgentTracer(
        user_id=user_id,
        username=username,
        session_id="upload-pending",
        query=f"Upload Excel file: {file.filename}",
        selected_agent="excel_reader_tool",
    )
    request.state.trace_id = tracer.trace_id
    await tracer.persist()
    
    if not file.filename.endswith((".xlsx", ".xls")):
        tracer.log_step("Validate Upload Type", status="failed", metadata={"filename": file.filename})
        tracer.finalize(
            summary="Upload rejected because only .xlsx and .xls files are supported.",
            agent_used="excel_reader_tool",
            status="failed",
        )
        await tracer.persist()
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported.")
        
    try:
        from app.db import files_col, chat_sessions_col, projects_col
        import bson

        # Handle project selection / creation on the fly
        resolved_project_id = project_id
        if new_project_name:
            tracer.start_step("Create Project")
            now_str = datetime.now(timezone.utc).isoformat()
            proj_doc = {
                "user_id": user_id,
                "project_name": new_project_name,
                "project_status": "Active",
                "project_start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "project_end_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
                "project_cost": 0.0,
                "project_description": f"On-the-fly created project for {new_project_name}",
                "created_at": now_str,
                "updated_at": now_str
            }
            project_start = time.time()
            proj_res = await projects_col().insert_one(proj_doc)
            resolved_project_id = str(proj_res.inserted_id)
            tracer.log_db_op("insert_one", "projects", round((time.time() - project_start) * 1000, 2))
            tracer.end_step("Create Project", metadata={"project_id": resolved_project_id})

        # 1. Insert a placeholder file document to generate an _id
        tracer.start_step("Register Uploaded File")
        file_doc = {
            "user_id": user_id,
            "original_filename": file.filename,
            "processing_status": "processing",
            "project_id": resolved_project_id,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
        file_insert_start = time.time()
        file_res = await files_col().insert_one(file_doc)
        file_id = str(file_res.inserted_id)
        tracer.log_db_op("insert_one", "files", round((time.time() - file_insert_start) * 1000, 2))
        tracer.end_step("Register Uploaded File", metadata={"file_id": file_id, "filename": file.filename})
        
        user_file_path = os.path.join(DATA_DIR, f"portfolio_{user_id}_{file_id}.xlsx")
        
        # Save file to user-specific location
        tracer.start_step("Save Excel To Disk")
        disk_start = time.time()
        with open(user_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_size = os.path.getsize(user_file_path)
        tracer.log_tool_call(
            tool_name="File Storage",
            tool_type="filesystem",
            input=file.filename,
            output=f"{file_size} bytes saved to {user_file_path}",
            latency_ms=round((time.time() - disk_start) * 1000, 2),
        )
        tracer.end_step("Save Excel To Disk", metadata={"file_path": user_file_path, "file_size": file_size})
            
        logger.info(f"File uploaded successfully and saved to {user_file_path} for user {user_id}")
        
        # Save custom mapping plan if provided
        plan_path = os.path.join(DATA_DIR, f"mapping_plan_{user_id}_{file_id}.json")
        plan = None
        if mapping_plan:
            try:
                tracer.start_step("Store Column Mapping Plan")
                plan = json.loads(mapping_plan)
                mapping_start = time.time()
                with open(plan_path, "w", encoding="utf-8") as pf:
                    json.dump(plan, pf, indent=2)
                tracer.log_tool_call(
                    tool_name="Column Mapping Plan",
                    tool_type="filesystem",
                    input="custom mapping JSON",
                    output=plan_path,
                    latency_ms=round((time.time() - mapping_start) * 1000, 2),
                )
                tracer.end_step("Store Column Mapping Plan", metadata={"plan_path": plan_path})
                logger.info(f"Custom mapping plan saved successfully to {plan_path} for user {user_id}")
            except Exception as pe:
                logger.error(f"Failed to parse custom mapping_plan: {pe}")
                tracer.log_error(pe, recovery_method="continue_without_custom_mapping")
        else:
            if os.path.exists(plan_path):
                os.remove(plan_path)

        # Test parse to validate format
        from app.tools.excel_reader import read_and_normalize_excel
        tracer.start_step("Parse And Normalize Excel")
        parse_start = time.time()
        df = read_and_normalize_excel(user_file_path, plan=plan, tracer=tracer)
        symbols = df["symbol"].unique().tolist()
        tracer.log_tool_call(
            tool_name="Excel Reader",
            tool_type="python",
            input=f"{file.filename} with {'custom' if plan else 'auto'} column mapping",
            output=f"Parsed {len(df)} transactions and {len(symbols)} unique symbols",
            latency_ms=round((time.time() - parse_start) * 1000, 2),
        )
        tracer.end_step(
            "Parse And Normalize Excel",
            metadata={
                "transaction_count": len(df),
                "unique_symbols": symbols[:10],
                "start_date": df["date"].min().strftime("%Y-%m-%d"),
                "end_date": df["date"].max().strftime("%Y-%m-%d"),
            },
        )
        
        tracer.start_step("Mark File Processed")
        file_update_start = time.time()
        await files_col().update_one(
            {"_id": file_res.inserted_id},
            {"$set": {
                "file_path": user_file_path,
                "file_size": file_size,
                "processing_status": "processed"
            }}
        )
        tracer.log_db_op("update_one", "files", round((time.time() - file_update_start) * 1000, 2))
        tracer.end_step("Mark File Processed")
        
        # Create a new Chat Session associated with this file
        tracer.start_step("Create Chat Session")
        session_doc = {
            "user_id": user_id,
            "file_id": file_id,
            "project_id": resolved_project_id,
            "original_filename": file.filename,
            "conversation_name": f"Chat on {file.filename}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        session_start = time.time()
        session_res = await chat_sessions_col().insert_one(session_doc)
        session_id = str(session_res.inserted_id)
        tracer.session_id = session_id
        tracer.log_db_op("insert_one", "chat_sessions", round((time.time() - session_start) * 1000, 2))
        tracer.end_step("Create Chat Session", metadata={"session_id": session_id})
        
        execution_time = time.time() - start_time
        
        summary = (
            f"Excel sheet uploaded and validated successfully. "
            f"Parsed {len(df)} transactions covering {len(symbols)} unique stocks "
            f"from {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}."
        )
        
        response = APIResponse(
            success=True,
            execution_time=round(execution_time, 4),
            agent_used="excel_reader_tool",
            summary=summary,
            insights=[
                f"Valid stock symbols parsed: {', '.join(symbols[:5])}" + (", ..." if len(symbols) > 5 else ""),
                "Standard columns successfully normalized."
            ],
            structured_data={
                "session_id": session_id,
                "file_id": file_id,
                "project_id": resolved_project_id,
                "transaction_count": len(df),
                "unique_symbols": symbols,
                "start_date": df["date"].min().strftime("%Y-%m-%d"),
                "end_date": df["date"].max().strftime("%Y-%m-%d")
            }
        )
        tracer.finalize(
            summary=summary,
            agent_used="excel_reader_tool",
            result_size_bytes=len(response.model_dump_json()),
            status="success",
        )
        await tracer.persist()
        return response
    except Exception as e:
        logger.error(f"Upload and validation failed: {mask_free_text(str(e))}")
        try:
            if 'user_file_path' in locals() and os.path.exists(user_file_path):
                os.remove(user_file_path)
        except Exception:
            pass
            
        execution_time = time.time() - start_time
        response = APIResponse(
            success=False,
            execution_time=round(execution_time, 4),
            agent_used="excel_reader_tool",
            summary=safe_user_visible_error(e),
            insights=[],
            structured_data={}
        )
        tracer.log_error(e)
        tracer.finalize(summary=response.summary, agent_used="excel_reader_tool", status="failed")
        await tracer.persist()
        return response


class ProjectCreateRequest(BaseModel):
    project_name: str
    project_status: Optional[str] = "Active"
    project_start_date: Optional[str] = None
    project_end_date: Optional[str] = None
    project_cost: Optional[float] = 0.0
    project_description: Optional[str] = ""

@router.post("/projects")
async def create_project(req: ProjectCreateRequest, current_user: dict = Depends(get_current_user)):
    from app.db import projects_col
    user_id = str(current_user["_id"])
    now_str = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_id": user_id,
        "project_name": req.project_name,
        "project_status": req.project_status,
        "project_start_date": req.project_start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "project_end_date": req.project_end_date or (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
        "project_cost": req.project_cost,
        "project_description": req.project_description,
        "created_at": now_str,
        "updated_at": now_str
    }
    res = await projects_col().insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return {"success": True, "project": doc}


@router.get("/projects")
async def list_projects(current_user: dict = Depends(get_current_user)):
    from app.db import projects_col
    user_id = str(current_user["_id"])
    cursor = projects_col().find({"user_id": user_id}).sort("created_at", -1)
    projects = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        projects.append(doc)
    return {"success": True, "projects": projects}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: str, current_user: dict = Depends(get_current_user)):
    from app.db import projects_col, files_col, chat_sessions_col
    import bson
    user_id = str(current_user["_id"])
    project = await projects_col().find_one({"_id": bson.ObjectId(project_id), "user_id": user_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project["_id"] = str(project["_id"])
    
    # Retrieve files in this project
    cursor = files_col().find({"project_id": project_id, "user_id": user_id}).sort("uploaded_at", -1)
    files = []
    async for f in cursor:
        f["_id"] = str(f["_id"])
        
        # Resolve session_id for this file
        session = await chat_sessions_col().find_one({"file_id": f["_id"], "user_id": user_id})
        session_id = str(session["_id"]) if session else None
        
        files.append({
            "file_id": f["_id"],
            "original_filename": f["original_filename"],
            "uploaded_at": f["uploaded_at"],
            "session_id": session_id
        })
        
    return {"success": True, "project": project, "files": files}


@router.get("/user/sessions")
async def list_user_sessions(current_user: dict = Depends(get_current_user)):
    from app.db import chat_sessions_col
    user_id = str(current_user["_id"])
    cursor = chat_sessions_col().find({"user_id": user_id}).sort("updated_at", -1)
    sessions = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        sessions.append(doc)
    return {"success": True, "sessions": sessions}


@router.get("/chat/history/{session_id}")
async def get_session_history(session_id: str, current_user: dict = Depends(get_current_user)):
    from app.db import chat_messages_col
    user_id = str(current_user["_id"])
    cursor = chat_messages_col().find({"session_id": session_id, "user_id": user_id}).sort("timestamp", 1)
    messages = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        
        # Parse timestamp to unix milliseconds
        ts = int(time.time() * 1000)
        if "timestamp" in doc:
            try:
                ts = int(datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                pass
                
        messages.append({
            "id": doc["_id"],
            "role": doc["role"],
            "content": doc["content"],
            "agentUsed": doc.get("agent_used"),
            "structuredData": doc.get("structured_data"),
            "insights": doc.get("insights"),
            "timestamp": ts
        })
    return {"success": True, "messages": messages}


@router.post("/agent/portfolio", response_model=APIResponse)
async def get_portfolio_summary(
    request: Request,
    session_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    return await run_workflow_on_file(current_user, request, selected_agent="portfolio_agent", passed_session_id=session_id)


@router.post("/agent/pnl", response_model=APIResponse)
async def get_pnl_summary(
    request: Request,
    session_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    return await run_workflow_on_file(current_user, request, selected_agent="pnl_agent", passed_session_id=session_id)


@router.post("/agent/dividend", response_model=APIResponse)
async def get_dividend_summary(
    request: Request,
    session_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    return await run_workflow_on_file(current_user, request, selected_agent="dividend_agent", passed_session_id=session_id)


@router.post("/agent/stock_analysis", response_model=APIResponse)
async def get_stock_analysis(request_body: ChatRequest, request: Request, current_user: dict = Depends(get_current_user)):
    return await run_workflow_on_file(
        current_user, request,
        selected_agent="stock_analysis_agent",
        message=request_body.message,
        passed_session_id=request_body.session_id
    )


@router.post("/chat", response_model=APIResponse)
async def chat(request_body: ChatRequest, request: Request, current_user: dict = Depends(get_current_user)):
    return await run_workflow_on_file(
        current_user, request,
        message=request_body.message,
        passed_session_id=request_body.session_id
    )


@router.delete("/user/sessions/{session_id}")
async def delete_user_session(session_id: str, current_user: dict = Depends(get_current_user)):
    from app.db import chat_sessions_col, chat_messages_col, traces_col, files_col
    import bson
    user_id = str(current_user["_id"])
    
    try:
        session_query = {"_id": bson.ObjectId(session_id), "user_id": user_id}
    except Exception:
        session_query = {"_id": session_id, "user_id": user_id}

    # Delete the session
    await chat_sessions_col().delete_one(session_query)
    
    # Delete associated messages, traces, and files
    await chat_messages_col().delete_many({"session_id": session_id, "user_id": user_id})
    await traces_col().delete_many({"session_id": session_id, "user_id": user_id})
    await files_col().delete_many({"session_id": session_id, "user_id": user_id})
    
    return {"success": True}
