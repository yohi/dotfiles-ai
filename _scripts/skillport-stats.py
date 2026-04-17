import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Tuple


def parse_input() -> Tuple[List[Dict[str, Any]], int]:
    try:
        input_data = sys.stdin.read()
        if not input_data:
            sys.stderr.write("No input data received.\n")
            sys.exit(1)
        data = json.loads(input_data)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error: Invalid JSON input: {e}\n")
        sys.exit(1)

    if not isinstance(data, dict):
        sys.stderr.write("Error: Input data is not a JSON object (dict).\n")
        sys.exit(1)

    skills = data.get("skills", [])
    if not isinstance(skills, list):
        sys.stderr.write("Error: 'skills' in JSON input is not a list.\n")
        sys.exit(1)

    total = data.get("total", len(skills))
    return skills, total


def get_env_status() -> Tuple[str, str, str]:
    mcp_gateway_status = os.environ.get("MCP_GATEWAY_STATUS", "unknown")
    skillport_mcp_version = os.environ.get("SKILLPORT_MCP_VERSION", "unknown")
    skillport_mcp_status = os.environ.get("SKILLPORT_MCP_STATUS", "unknown")
    return mcp_gateway_status, skillport_mcp_version, skillport_mcp_status


def print_stats(
    skills: List[Dict[str, Any]],
    total: int,
    mcp_gateway_status: str,
    skillport_mcp_version: str,
    skillport_mcp_status: str,
) -> None:
    namespace_counts: Counter[str] = Counter()
    root_skills = []

    for skill in skills:
        if not isinstance(skill, dict):
            sys.stderr.write(f"Error: skill entry is not a dict: {skill}\n")
            sys.exit(1)

        skill_id = skill.get("id", "")
        if not isinstance(skill_id, str):
            sys.stderr.write(f"Error: skill id is not a string: {skill_id}\n")
            sys.exit(1)

        if "/" in skill_id:
            ns = skill_id.split("/")[0]
            namespace_counts[ns] += 1
        else:
            namespace_counts["(root)"] += 1
            root_skills.append(skill_id)

    print("\n📊 SkillPort Stats")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Total Skills: {total}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Service Status")
    print("────────────────────────────────────────")

    gateway_icon = "✅" if mcp_gateway_status == "active" else "❌"
    # "active (Gateway)" なども許容するため startswith("active") を使用
    mcp_icon = "✅" if skillport_mcp_status.startswith("active") else "❌"

    print(f"Docker MCP Gateway: {gateway_icon} {mcp_gateway_status}")
    print(f"SkillPort MCP Status: {mcp_icon} {skillport_mcp_status}")
    print(f"SkillPort MCP Tool:   📦 {skillport_mcp_version}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"{'Namespace':<25} {'Count':<5}")
    print("────────────────────────────────────────")

    # カテゴリごとのカウントを表示(降順、(root)は最後または先頭にするなど調整可能)
    for ns, count in sorted(namespace_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{ns:<25} {count:<5}")

    if root_skills:
        print("────────────────────────────────────────")
        print("Individual Skills (root):")
        for skill_id in sorted(root_skills):
            print(f"  - {skill_id}")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def main() -> None:
    skills, total = parse_input()
    gw_status, mcp_ver, mcp_status = get_env_status()
    print_stats(skills, total, gw_status, mcp_ver, mcp_status)


if __name__ == "__main__":
    main()
