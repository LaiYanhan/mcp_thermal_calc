"""
一键可视化启动与脱离 Agent 调试脚本 (Standalone Pipeline & Operator Debugger)

支持启动可视化流程与参数核对服务，可指定渲染任意 pipeline 文件或已注册流水线。

运行方式示例:
    # 1. 默认启动电加热器熔盐储热基准场景:
    python run_web.py

    # 2. 明确指定调试电加热器熔盐储热流水线:
    python run_web.py -p electric_heater_salt_steam

    # 3. 指定调试新建的工业热泵储能供汽流水线，并重置画布:
    python run_web.py -p industrial_heat_pump_steam --reset

    # 4. 直接进入阶段 02 参数核对与计算结果界面:
    python run_web.py --debug -p industrial_heat_pump_steam -s 2

    # 5. 查看当前系统中所有已注册的可选流水线清单:
    python run_web.py --list
"""

import argparse
import sys
import threading
import time
import webbrowser
import uvicorn
import pipelines  # noqa: F401 (确保内置管道自动加载注册)
from core.pipeline import pipeline_registry
from server.web_app import app, WEB_SERVER_HOST, WEB_SERVER_PORT


def parse_args():
    parser = argparse.ArgumentParser(
        description="工业热工流程与参数可视化调试工具 (可脱离 Agent 独立运行)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用示例:
  python run_web.py                                                  # 默认启动电加热器熔盐储热基准场景
  python run_web.py -p electric_heater_salt_steam                    # 指定调试电加热器熔盐储热流水线
  python run_web.py -p industrial_heat_pump_steam                    # 指定调试工业热泵储能供汽流水线
  python run_web.py -p industrial_heat_pump_steam --reset            # 强制清空缓存并重绘热泵图纸
  python run_web.py --list                                           # 打印全部已注册流水线清单
        """
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="启用前端阶段切换与确认计算按钮；默认由 AI 通过 MCP 推进流程"
    )
    parser.add_argument(
        "-p", "--pipeline",
        default="scenario_electric_heater_salt_steam",
        help="指定要渲染和调试的流水线 (支持 Pipeline ID、模块名或 .py 文件路径，默认: scenario_electric_heater_salt_steam)"
    )
    parser.add_argument(
        "-s", "--stage",
        type=int,
        default=1,
        choices=[1, 2],
        help="指定启动时打开的阶段 (1: 流程拓扑审核; 2: 参数核对与计算, 默认: 1)"
    )
    parser.add_argument(
        "-r", "--reset",
        action="store_true",
        help="强制以代码最新定义重置调试会话（清空过往临时草稿与排版缓存）"
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="打印当前系统中所有可用的流水线清单并退出"
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="自定义会话标识 (默认依据流水线 ID 自动生成专用会话)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=WEB_SERVER_PORT,
        help=f"Web 服务监听端口 (默认: {WEB_SERVER_PORT})"
    )
    parser.add_argument(
        "--host",
        default=WEB_SERVER_HOST,
        help=f"Web 服务监听地址 (默认: {WEB_SERVER_HOST})"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动唤起系统默认浏览器"
    )
    args = parser.parse_args()
    if args.stage != 1 and not args.debug:
        parser.error("--stage 2 仅可与 --debug 一起使用；正常模式由 AI 切换阶段")
    return args


def print_registered_pipelines():
    all_pipelines = pipeline_registry.list_all()
    print("\n" + "=" * 60)
    print(" 当前系统已注册的计算管道清单 (Registered Pipelines)")
    print("=" * 60)
    for idx, p in enumerate(all_pipelines, 1):
        print(f" [{idx}] ID: {p.id}")
        print(f"     名称: {p.name} (分类: {p.category})")
        print(f"     步骤数: {len(p.steps)} 个算子 | 输入参数: {len(p.required_inputs)} 项")
        if p.description:
            summary = p.description.replace("\n", " ").strip()
            print(f"     简介: {summary[:80]}...")
        print("-" * 60)
    print(f"共发现 {len(all_pipelines)} 条计算管道。可通过 `python run_web.py -p <ID>` 指定调试。\n")


def open_browser(target_url: str):
    time.sleep(1.2)
    print(f"\n[INFO] 已自动为您打开可视化流程编辑器: {target_url}\n")
    webbrowser.open(target_url)


def main():
    args = parse_args()
    app.state.editor_debug = args.debug

    if args.list:
        print_registered_pipelines()
        sys.exit(0)

    try:
        pipeline = pipeline_registry.resolve(args.pipeline)
    except KeyError as e:
        print(f"\n[ERROR] {e}")
        print_registered_pipelines()
        sys.exit(1)

    session_id = args.session_id or f"debug_{pipeline.id}"
    reset_query = "&reset=1" if args.reset else ""
    editor_url = f"http://{args.host}:{args.port}/editor?session_id={session_id}&pipeline={pipeline.id}&stage={args.stage}{reset_query}"

    if not args.no_browser:
        threading.Thread(target=open_browser, args=(editor_url,), daemon=True).start()

    print("=" * 60)
    print(" 工业热工计算与选型测算系统 // 本地可视化调试服务启动")
    print(f" 当前调试流水线: 【{pipeline.name}】 ({pipeline.id})")
    print(f" 拓扑规模: {len(p_steps := pipeline.steps)} 个算子步骤, {len(pipeline.required_inputs)} 个输入/常量")
    print(f" 阶段设定: 阶段 0{args.stage} ({'流程拓扑审核' if args.stage == 1 else '参数核对与计算'})")
    print(f" 阶段控制: {'前端调试（--debug）' if args.debug else 'AI / MCP'}")
    if args.reset:
        print(" 会话模式: 已启用 --reset，将强制丢弃历史草稿并重新初始化")
    print(f" 服务地址: http://{args.host}:{args.port}")
    print(f" 直达链接: {editor_url}")
    print(" 按 Ctrl+C 可随时停止服务")
    print("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
