import json
import sys
from collections import Counter, defaultdict

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print("No input data received.")
            return
        data = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}")
        sys.exit(1)

    skills = data.get("skills", [])
    total = data.get("total", len(skills))

    namespace_counts = Counter()
    root_skills = []
    
    for skill in skills:
        skill_id = skill.get("id", "")
        if "/" in skill_id:
            ns = skill_id.split("/")[0]
            namespace_counts[ns] += 1
        else:
            namespace_counts["(root)"] += 1
            root_skills.append(skill_id)

    print(f"\n📊 SkillPort Stats")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Total Skills: {total}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"{'Namespace':<25} {'Count':<5}")
    print(f"────────────────────────────────────────")
    
    # カテゴリごとのカウントを表示（降順、(root)は最後または先頭にするなど調整可能）
    for ns, count in sorted(namespace_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{ns:<25} {count:<5}")
        
    if root_skills:
        print(f"────────────────────────────────────────")
        print(f"Individual Skills (root):")
        for skill_id in sorted(root_skills):
            print(f"  - {skill_id}")
            
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

if __name__ == "__main__":
    main()
