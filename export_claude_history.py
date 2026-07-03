#!/usr/bin/env python3
"""
Claude Code 会话批量导出工具

功能：扫描 Claude Code CLI 的会话存储目录，导出完整的对话记录（用户消息 + AI 回复）为 Markdown 文件。

数据源：
- 主数据源: ~/.claude/projects/{project-name}/{sessionId}.jsonl
- 辅助数据: ~/.claude/history.jsonl

输出：
- 目录: 当前工作目录下的 conversations/ (可通过 --output 参数自定义)
- 格式: {时间戳}-{首条消息摘要}.md
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path


def get_claude_home() -> Path:
    """获取 Claude Code 配置目录"""
    user_profile = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    return Path(user_profile) / ".claude"


def discover_sessions(claude_home: Path) -> dict:
    """
    扫描 projects 目录，发现所有会话文件
    
    Returns:
        dict: {session_id: {"project_dir": Path, "file": Path, "cwd": str}}
    """
    projects_dir = claude_home / "projects"
    sessions = {}
    
    if not projects_dir.exists():
        print(f"警告: 项目目录不存在: {projects_dir}")
        return sessions
    
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        
        for jsonl_file in project_dir.glob("*.jsonl"):
            # 跳过子代理(subagent)的会话文件
            if "subagents" in str(jsonl_file):
                continue
                
            session_id = jsonl_file.stem
            sessions[session_id] = {
                "project_dir": project_dir,
                "file": jsonl_file,
                "project_name": project_dir.name,
                "cwd": None
            }
    
    return sessions


def parse_message_content(msg: dict) -> list:
    """
    解析消息内容，提取文本片段
    
    Args:
        msg: 消息字典
        
    Returns:
        list: 文本内容列表
    """
    contents = []
    
    # 处理用户消息 (直接字符串或content数组)
    if msg.get("type") == "user":
        message = msg.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                contents.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            contents.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            tool_content = item.get("content", "")
                            if isinstance(tool_content, str):
                                contents.append(f"[工具结果] {tool_content[:200]}...")
    
    # 处理助手消息
    elif msg.get("type") == "assistant":
        message = msg.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        
                        if item_type == "text":
                            text = item.get("text", "")
                            if text:
                                contents.append(text)
                        
                        elif item_type == "thinking":
                            thinking = item.get("thinking", "")
                            if thinking:
                                contents.append(f"[思考] {thinking}")
                        
                        elif item_type == "tool_use":
                            tool_name = item.get("name", "")
                            tool_input = item.get("input", {})
                            contents.append(f"[工具调用] {tool_name}: {json.dumps(tool_input, ensure_ascii=False)[:200]}")
    
    return contents


def parse_timestamp(ts_str: str) -> datetime:
    """
    解析 ISO 8601 时间戳为本地时间
    
    Args:
        ts_str: ISO 8601 格式时间戳
        
    Returns:
        datetime: 本地时间
    """
    try:
        # 处理带 Z 的 UTC 时间
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_str)
        # 转换为本地时间
        return dt.astimezone()
    except (ValueError, TypeError):
        return datetime.now()


def format_timestamp(dt: datetime) -> str:
    """格式化时间为可读字符串"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def extract_summary(text: str, max_length: int = 30) -> str:
    """
    从文本中提取摘要
    
    Args:
        text: 原始文本
        max_length: 最大长度
        
    Returns:
        str: 摘要文本
    """
    if not text:
        return "无标题"
    
    # 移除换行和多余空格
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 截断到指定长度
    if len(text) > max_length:
        return text[:max_length] + "..."
    
    return text


def sanitize_filename(name: str) -> str:
    """
    清理文件名中的非法字符和特殊符号
    
    保留中文、英文、数字，移除其他特殊字符
    
    Args:
        name: 原始文件名
        
    Returns:
        str: 安全的文件名
    """
    # 移除特殊字符: @ , 括号 空格等
    # 保留中文、英文、数字、下划线、连字符
    safe_name = re.sub(r'[@,，、。！？；：""''（）【】《》\s\(\)\[\]\{\}]', '', name)
    
    # Windows 文件名不能包含: \ / : * ? " < > |
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', safe_name)
    
    # 移除可能导致问题的字符
    safe_name = re.sub(r'[\s\.]+$', '', safe_name)
    
    # 移除开头的点和空格
    safe_name = safe_name.lstrip('. ')
    
    # 如果清理后为空，使用默认名称
    if not safe_name:
        return "无标题"
    
    return safe_name


def generate_filename(session_info: dict, start_time: datetime) -> str:
    """
    生成安全的文件名
    
    格式: {时间戳}-{工作目录最后一个单词}.md
    示例: 20260509_101730-claude_code.md
    
    Args:
        session_info: 会话信息
        start_time: 会话开始时间
        
    Returns:
        str: 安全的文件名
    """
    # 时间戳格式: 年月日_时分秒
    time_str = start_time.strftime("%Y%m%d_%H%M%S")
    
    # 获取工作目录名
    cwd = session_info.get("cwd", "")
    if cwd:
        raw_name = Path(cwd).name
    else:
        raw_name = session_info.get("project_name", "unknown")
    
    # 提取最后一个单词（按 - 拆分）
    normalized = raw_name.replace('_', '-').replace('\\', '-').replace('/', '-')
    parts = [p for p in normalized.split('-') if p]
    
    if not parts:
        last_word = "unknown"
    else:
        last_word = parts[-1]
    
    # 清理非法字符
    safe_name = sanitize_filename(last_word)
    
    return f"{time_str}-{safe_name}.md"


def export_session(session_id: str, session_info: dict, output_dir: Path) -> bool:
    """
    导出单个会话为 Markdown 文件
    
    Args:
        session_id: 会话ID
        session_info: 会话信息
        output_dir: 输出目录
        
    Returns:
        bool: 是否成功
    """
    jsonl_file = session_info["file"]
    
    if not jsonl_file.exists():
        print(f"  跳过: 文件不存在 {jsonl_file}")
        return False
    
    messages = []
    start_time = None
    cwd = None
    
    try:
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # 提取时间戳
                ts_str = msg.get("timestamp", "")
                if ts_str:
                    msg_time = parse_timestamp(ts_str)
                    if start_time is None:
                        start_time = msg_time
                
                # 提取工作目录
                if cwd is None:
                    cwd = msg.get("cwd", "")
                    if cwd:
                        session_info["cwd"] = cwd
                
                # 只处理用户和助手消息
                msg_type = msg.get("type", "")
                if msg_type not in ("user", "assistant"):
                    continue
                
                # 解析消息内容
                contents = parse_message_content(msg)
                if not contents:
                    continue
                
                messages.append({
                    "type": msg_type,
                    "time": msg_time if ts_str else datetime.now(),
                    "contents": contents
                })
    
    except Exception as e:
        print(f"  错误: 读取文件失败 {jsonl_file}: {e}")
        return False
    
    if not messages:
        print(f"  跳过: 无有效消息 {session_id}")
        return False
    
    # 确定开始时间和工作目录
    if start_time is None:
        start_time = datetime.now()
    
    if cwd:
        session_info["cwd"] = cwd
    
    # 生成文件名
    filename = generate_filename(session_info, start_time)
    output_path = output_dir / filename
    
    # 处理文件名冲突
    counter = 1
    original_path = output_path
    while output_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        output_path = output_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    
    # 生成 Markdown 内容
    md_content = generate_markdown(session_id, session_info, messages, start_time)
    
    # 写入文件
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  已导出: {output_path.name}")
        return True
    except Exception as e:
        print(f"  错误: 写入文件失败 {output_path}: {e}")
        return False


def generate_markdown(session_id: str, session_info: dict, messages: list, start_time: datetime) -> str:
    """
    生成 Markdown 文档内容
    
    Args:
        session_id: 会话ID
        session_info: 会话信息
        messages: 消息列表
        start_time: 开始时间
        
    Returns:
        str: Markdown 内容
    """
    cwd = session_info.get("cwd", "")
    project_name = session_info.get("project_name", "")
    
    lines = [
        "# Claude Code 会话记录",
        "",
        "## 会话信息",
        f"- **会话ID**: `{session_id}`",
        f"- **工作目录**: `{cwd or project_name}`",
        f"- **开始时间**: {format_timestamp(start_time)}",
        f"- **消息数量**: {len(messages)}",
        "",
        "---",
        "",
        "## 对话记录",
        "",
    ]
    
    for msg in messages:
        time_str = format_timestamp(msg["time"])
        sender = "用户" if msg["type"] == "user" else "AI"
        
        lines.append(f"### [{time_str}] {sender}")
        lines.append("")
        
        for content in msg["contents"]:
            # 转义 Markdown 特殊字符
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            lines.append(content)
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Claude Code 会话批量导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python export_claude_conversations.py                    # 导出到 ./conversations/
  python export_claude_conversations.py -o ./my-exports    # 导出到 ./my-exports/
  python export_claude_conversations.py --output /path/to  # 导出到指定目录
        """
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出目录路径 (默认: ./conversations/)"
    )
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("Claude Code 会话批量导出工具")
    print("=" * 50)
    
    # 获取 Claude Home
    claude_home = get_claude_home()
    print(f"\nClaude Home: {claude_home}")
    
    if not claude_home.exists():
        print(f"错误: Claude Code 配置目录不存在: {claude_home}")
        print("请确认 Claude Code 已安装并使用过。")
        return
    
    # 发现会话
    print("\n正在扫描会话文件...")
    sessions = discover_sessions(claude_home)
    print(f"发现 {len(sessions)} 个会话")
    
    if not sessions:
        print("未找到任何会话文件。")
        return
    
    # 确定输出目录
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path.cwd() / "conversations"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")
    
    # 导出会话
    print("\n开始导出...")
    success_count = 0
    fail_count = 0
    
    for idx, (session_id, session_info) in enumerate(sessions.items(), 1):
        print(f"\n[{idx}/{len(sessions)}] 处理会话: {session_id[:8]}...")
        
        if export_session(session_id, session_info, output_dir):
            success_count += 1
        else:
            fail_count += 1
    
    # 统计
    print("\n" + "=" * 50)
    print("导出完成!")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  总计: {len(sessions)}")
    print(f"  输出: {output_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
