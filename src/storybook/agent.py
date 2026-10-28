"""Inspectable LangChain tool execution with model or explicit demo planning.

This executor never sends a request itself. The caller supplies the permitted
planner and generation functions, so demo mode cannot silently call paid APIs.
"""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from typing import Callable


PIPELINE = ("write_story", "generate_images", "generate_audio", "render_video")
OPTIONAL_TOOLS = ("retrieve_materials", "review_story")
TOOL_LABELS = {"write_story": "结构化故事写作", "generate_images": "场景插画", "generate_audio": "多角色配音", "render_video": "视频合成", "revise_story": "依据用户干预修订故事", "retrieve_materials": "检索相关故事素材并加入创作上下文", "review_story": "只读检查故事结构，不修改正文"}


def validate_plan(plan: list[str], available_tools=None) -> list[str]:
    if not isinstance(plan, list) or not all(isinstance(name, str) for name in plan):
        raise ValueError("规划器必须返回工具名称字符串列表。")
    permitted = set(PIPELINE + OPTIONAL_TOOLS)
    if available_tools is not None:
        permitted &= set(available_tools)
    unknown = [name for name in plan if name not in permitted]
    if unknown:
        raise ValueError("规划包含未授权工具：" + ", ".join(unknown))
    if len(plan) < 4 or not set(PIPELINE).issubset(plan):
        raise ValueError("完整规划必须包含写作、绘图、配音、视频四个工具。")
    if len(plan) > 20:
        raise ValueError("单次规划最多20步，避免无界重复调用。")
    completed = set()
    for name in plan:
        if name == "write_story":
            completed = {"write_story"}
        elif name == "generate_images":
            if "write_story" not in completed:
                raise ValueError("依赖顺序错误：绘图前必须完成写作。")
            completed.discard("render_video")
            completed.add(name)
        elif name == "generate_audio":
            if not {"write_story", "generate_images"}.issubset(completed):
                raise ValueError("依赖顺序错误：配音前必须完成写作和绘图。")
            completed.discard("render_video")
            completed.add(name)
        elif name == "render_video":
            if not set(PIPELINE[:-1]).issubset(completed):
                raise ValueError("依赖顺序错误：视频前必须完成写作、绘图和配音。")
            completed.add(name)
        elif name == "review_story":
            if "write_story" not in completed:
                raise ValueError("审查故事前必须先完成写作。")
            # The registered review tool is read-only; actual revisions use
            # revise_story and explicitly invalidate all derivative media.
            completed.add(name)
    if not set(PIPELINE).issubset(completed):
        raise ValueError("规划结束时须保留与最新故事关联的完整图像、音频和视频。")
    return plan


async def run_agent(project: dict, tools: dict[str, Callable], planner: Callable | None, job: dict, save_project: Callable) -> dict:
    """Run four real StructuredTools, accepting interventions between calls.

    Tool callbacks return an updated Project; they take no arguments except the
    optional revise_story callback, which accepts one instruction string.
    save_project(project) may be sync or async. Trace is returned and attached to
    job.result so the caller can persist it as JSON/Markdown in its project dir.
    """
    trace: list[dict] = []
    planning_mode = "model" if planner is not None else "demo_rules"
    job.setdefault("logs", [])
    job.setdefault("steps", [])
    job.update(status="running", progress=0)

    def log(message: str, event: str, tool: str = "", **extra) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        job["logs"].append({"time": now, "message": message})
        trace.append({"time": now, "event": event, "tool": tool, "message": message, **extra})

    async def persist() -> None:
        result = save_project(project)
        if inspect.isawaitable(result):
            await result

    def adopt(updated: dict) -> dict:
        if not isinstance(updated, dict):
            raise TypeError("工具必须返回更新后的Project字典。")
        if updated is not project:
            project.clear()
            project.update(updated)
        return project

    async def plan_for(instruction: str) -> list[str]:
        if planner is None:
            log("本地演示采用公开固定规则规划；未调用模型规划器。", "planning", planning_mode="demo_rules", instruction=instruction)
            return list(PIPELINE)
        log("请求模型选择素材检索、故事审查、重试与多模态创作步骤。", "planning", planning_mode="model", instruction=instruction)
        result = planner(instruction, project)
        if inspect.isawaitable(result):
            result = await result
        return validate_plan(result, tools)

    try:
        try:
            from langchain_core.tools import StructuredTool
        except ImportError as exc:
            raise RuntimeError("缺少 langchain-core；无法注册或执行LangChain工具，请先安装requirements.txt。") from exc
        missing = [name for name in PIPELINE if name not in tools or not callable(tools[name])]
        if missing:
            raise ValueError("缺少可调用工具：" + ", ".join(missing))

        def make_callback(name: str):
            async def invoke() -> dict:
                value = tools[name]()
                if inspect.isawaitable(value):
                    value = await value
                return adopt(value)
            return invoke

        registered = {name: StructuredTool.from_function(coroutine=make_callback(name), name=name, description=TOOL_LABELS[name]) for name in PIPELINE + OPTIONAL_TOOLS if callable(tools.get(name))}
        revise_tool = None
        if callable(tools.get("revise_story")):
            async def revise(instruction: str) -> dict:
                value = tools["revise_story"](instruction)
                if inspect.isawaitable(value):
                    value = await value
                return adopt(value)
            revise_tool = StructuredTool.from_function(coroutine=revise, name="revise_story", description=TOOL_LABELS["revise_story"])
        log("已使用LangChain StructuredTool实际注册创作工具及可用的检索/审查工具。", "registered", registered_tools=list(registered))
        plan = validate_plan(await plan_for(str(job.get("instruction", ""))), registered)
        job["steps"] = [{"name": name, "label": TOOL_LABELS[name], "status": "queued"} for name in plan]
        log("已验证工具白名单及依赖顺序。", "plan_validated", plan=list(plan))
        done: set[str] = set()
        paused_once = False
        index = 0
        interventions = 0
        superseded_write_index = None

        while index < len(plan):
            name = plan[index]
            if index == superseded_write_index:
                job["steps"][index]["status"] = "completed"
                log("用户修订已提供最新故事，复用该文本继续执行模型规划。", "reused_revised_story", name)
                superseded_write_index = None
                index += 1
                continue
            if "write_story" in done and job.get("pause_after_story") and not paused_once:
                paused_once = True
                job.update(status="paused", progress=max(int(job.get("progress", 0)), 25))
                log("故事已生成，等待用户检查、干预并点击继续。", "paused")
                while not job.get("resume_requested"):
                    await asyncio.sleep(0.15)
                job["resume_requested"] = False
                job["status"] = "running"
                log("用户恢复执行，继续前检查待处理指令。", "resumed")

            # Apply even an instruction queued before startup after initial
            # writing, so all four advertised production tools are actually run.
            instruction = str(job.pop("pending_instruction", "") or "").strip() if "write_story" in done else ""
            if instruction:
                if revise_tool is None:
                    raise ValueError("收到用户干预，但未注册revise_story修订工具。")
                interventions += 1
                if interventions > 20:
                    raise ValueError("单次流程干预次数超过20次，请启动新流程。")
                log("处理用户干预并通过修订工具更新故事。", "intervention", "revise_story", instruction=instruction)
                await revise_tool.ainvoke({"instruction": instruction})
                await persist()
                replanned = validate_plan(await plan_for(instruction), registered)
                # The revised story supersedes writing. All derivative media are
                # deliberately regenerated, including media completed before it.
                done = {"write_story"}
                plan = replanned
                index = 0
                superseded_write_index = plan.index("write_story")
                job["steps"] = [{"name": tool_name, "label": TOOL_LABELS[tool_name], "status": "queued"} for tool_name in plan]
                log("故事修订完成，依据新规划重新生成衍生媒体以保持一致。", "replanned", plan=list(plan))
                continue

            step = job["steps"][index]
            step["status"] = "running"
            log(f"开始：{TOOL_LABELS[name]}", "tool_start", name, framework="langchain_core.StructuredTool")
            await registered[name].ainvoke({})
            done.add(name)
            step["status"] = "completed"
            job["progress"] = round(100 * (index + 1) / len(plan))
            await persist()
            log(f"完成：{TOOL_LABELS[name]}", "tool_end", name)
            index += 1
            # Yield to the UI between all steps, including fast local demo tools.
            await asyncio.sleep(0.05)

        job.update(status="completed", progress=100)
        log("创作流程完成。", "completed")
        result = {"project": project, "project_id": project.get("id"), "planning_mode": planning_mode,
                  "framework": "langchain_core.StructuredTool", "registered_tools": list(registered), "trace": trace}
        job["result"] = {key: value for key, value in result.items() if key != "project"}
        return result
    except asyncio.CancelledError:
        job.update(status="failed", error="流程已取消。")
        log("流程已取消。", "cancelled")
        job["result"] = {"planning_mode": planning_mode, "trace": trace}
        raise
    except Exception as exc:
        job.update(status="failed", error=str(exc))
        for step in job.get("steps", []):
            if step.get("status") == "running":
                step["status"] = "failed"
        log(f"流程失败：{exc}", "failed")
        job["result"] = {"planning_mode": planning_mode, "trace": trace}
        raise
