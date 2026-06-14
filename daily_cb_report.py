"""
可转债早报 - 微信推送格式化脚本
用于 cron 定时任务，输出格式化消息文本 + Excel 报告路径
"""

import os
import re
import subprocess
from datetime import datetime

HOLDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def read_holdings() -> list[tuple[str, str]]:
    """读取持仓转债 (code, name)"""
    entries = []
    if not os.path.exists(HOLDINGS_FILE):
        return entries
    with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                entries.append((parts[0], parts[1]))
            elif len(parts) == 1:
                entries.append((parts[0], parts[0]))
    return entries


def run_screening(codes: list[str]) -> tuple[str, str | None]:
    """运行 main.py，返回 (控制台输出文本, 最新Excel路径)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(script_dir, "main.py")
    venv_python = os.path.join(script_dir, ".venv", "Scripts", "python.exe")

    cmd = [venv_python, main_py, "--mode", "full", "--output", "both"]
    if codes:
        cmd.extend(["--codes", ",".join(codes)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    full_output = result.stdout + "\n" + result.stderr

    # 找最新 Excel
    latest_excel = None
    if os.path.exists(OUTPUT_DIR):
        excels = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("筛选报告_") and f.endswith(".xlsx")]
        if excels:
            latest_excel = max(
                [os.path.join(OUTPUT_DIR, f) for f in excels],
                key=os.path.getmtime,
            )
    return full_output, latest_excel


def format_wechat(output_text: str, excel_path: str | None, holdings: list[tuple[str, str]]) -> str:
    """生成微信消息"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = output_text.split("\n")
    parts = [f"📊 可转债早报 | {today}", ""]

    # ---- 持仓分析 ----
    parts.append("━" * 22)
    parts.append("📌 你的持仓")
    parts.append("━" * 22)

    # 从详情区块提取持仓信息
    holdings_detail = {}  # code -> dict
    current_detail = None
    for line in lines:
        m = re.search(r'=== (.+)（(\d+)）详情 ===', line)
        if m:
            current_detail = {"name": m.group(1).strip(), "code": m.group(2)}
            holdings_detail[current_detail["code"]] = current_detail
            continue
        if current_detail:
            if "【综合判定】" in line:
                vm = re.search(r'\[(.+?)\].*评分:\s*([\d.]+)', line)
                if vm:
                    current_detail["verdict"] = vm.group(1)
                    current_detail["score"] = vm.group(2)
            elif "【投资推荐】" in line:
                vm = re.search(r'★(.+?)\s*\(推荐分:\s*([\d.]+)\)', line)
                if vm:
                    current_detail["invest_level"] = "★" + vm.group(1)
                    current_detail["invest_score"] = vm.group(2)
            elif "原因:" in line:
                current_detail["reason"] = line.split("原因:")[1].strip()
            elif "排除结论:" in line:
                current_detail["exclusion"] = line.split("排除结论:")[1].strip()
            elif "===" in line and not re.search(r'=== .+（\d+）详情 ===', line):
                current_detail = None

    # 从表格中找持仓行
    in_table = False
    bond_rows = []  # list of dict
    for line in lines:
        if "转债名称" in line and "现价" in line and "推荐分" in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("=="):
                in_table = False
                continue
            if not line.strip() or line.strip().startswith("---"):
                continue
            cols = line.strip().split()
            if len(cols) >= 9:
                bond_rows.append({
                    "name": cols[0],
                    "price": cols[1],
                    "premium": cols[3],
                    "rating": cols[4],
                    "exclusions": cols[5],
                    "fin_score": cols[6],
                    "invest_score": cols[7],
                    "level": " ".join(cols[8:]),
                })

    # 匹配持仓
    holding_names = {n: c for c, n in holdings}
    for row in bond_rows:
        code = holding_names.get(row["name"])
        if not code:
            continue
        detail = holdings_detail.get(code, {})
        parts.append(f"▪ {row['name']}  {row['price']}元")
        parts.append(f"  评级{row['rating']} | 财务{row['fin_score']} | 推荐{row['invest_score']}")
        if row["exclusions"] != "0":
            parts.append(f"  ⚠️ 排除项: {row['exclusions']}条")
        reasons = []
        if detail.get("reason"):
            reasons.append(detail['reason'])
        elif row["level"].strip():
            reasons.append(row['level'].strip())
        if detail.get("exclusion"):
            reasons.append(f"排除: {detail['exclusion']}")
        if reasons:
            parts.append(f"  💬 {' | '.join(reasons)}")
        parts.append("")

    if not any(holding_names.get(row["name"]) for row in bond_rows):
        parts.append("（持仓转债未出现在今日筛选结果中）")
        parts.append("")

    # ---- 今日推荐 TOP5 ----
    parts.append("━" * 22)
    parts.append("🏆 推荐 TOP5")
    parts.append("━" * 22)

    # 收集非排除且得分高的转债
    candidates = []
    for row in bond_rows:
        try:
            sc = float(row["invest_score"])
            excl = int(row["exclusions"]) if row["exclusions"].isdigit() else 0
            if sc > 0 and excl < 2:
                candidates.append((sc, row))
        except ValueError:
            pass
    candidates.sort(key=lambda x: x[0], reverse=True)

    for i, (sc, row) in enumerate(candidates[:5]):
        parts.append(f"{i+1}. {row['name']}  {row['price']}元  ★{row['invest_score']}")
        # reason
        code = holding_names.get(row["name"], "")
        detail = holdings_detail.get(code, {})
        reason = detail.get("reason", "")
        if reason:
            parts.append(f"   {reason}")
        parts.append("")

    if not candidates:
        parts.append("  （无可推荐转债）")
        parts.append("")

    # ---- 排除预警 ----
    parts.append("━" * 22)
    parts.append("⚠️ 排除预警")
    parts.append("━" * 22)

    for row in bond_rows:
        try:
            excl = int(row["exclusions"]) if row["exclusions"].isdigit() else 0
            if excl >= 2:
                detail = holdings_detail.get(holding_names.get(row["name"], ""), {})
                reason = detail.get("exclusion", "")
                parts.append(f"  {row['name']} — 触犯{excl}条排除")
                if reason:
                    parts.append(f"    理由: {reason}")
        except ValueError:
            pass

    if not any(int(r["exclusions"]) >= 2 for r in bond_rows if r["exclusions"].isdigit()):
        parts.append("  无强制排除转债")
    parts.append("")

    # ---- 附件 ----
    if excel_path:
        parts.append(f"📎 {os.path.basename(excel_path)}")

    parts.append("")
    parts.append("━━━━━━━━━━━━━━━━━━━")
    parts.append("星尘 · 自动生成")

    return "\n".join(parts)


def main():
    holdings = read_holdings()
    codes = [c for c, _ in holdings]
    print(f"[早报] 持仓: {holdings}")

    output_text, excel_path = run_screening(codes)
    print(f"[早报] 筛选完成")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 保存原始输出
    with open(os.path.join(OUTPUT_DIR, "latest_output.txt"), "w", encoding="utf-8") as f:
        f.write(output_text)

    # 生成微信消息
    message = format_wechat(output_text, excel_path, holdings)
    with open(os.path.join(OUTPUT_DIR, "latest_msg.txt"), "w", encoding="utf-8") as f:
        f.write(message)

    print(f"[早报] 消息已保存")
    print("=" * 40)
    print("MESSAGE_START")
    print(message)
    print("MESSAGE_END")
    if excel_path:
        print(f"EXCEL_PATH:{excel_path}")


if __name__ == "__main__":
    main()
